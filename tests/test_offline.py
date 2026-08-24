# -*- coding: utf-8 -*-
"""تست‌های آفلاین — بدون نیاز به اینترنت؛ پاسخ‌های دیوار شبیه‌سازی شده‌اند."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from marketing_divar.client import DivarAuthError, DivarClient  # noqa: E402
from marketing_divar.db import (connect, export_csv, set_phone,  # noqa: E402
                                stats, upsert_lead)

# ------------------------------------------------------------- نمونه پاسخ‌ها --
SEARCH_RESPONSE = {
    "web_widgets": {
        "post_list": [
            {"data": {"token": "gZtQ1", "title": "آپارتمان ۸۰ متری",
                      "middle_description_text": "ودیعه ۵۰۰",
                      "top_description_text": "تهران، پونک",
                      "bottom_description_text": "۱ ساعت پیش",
                      "has_chat": True}},
            {"data": {"token": "kYw3A", "title": "آپارتمان ۱۲۰ متری",
                      "middle_description_text": "ودیعه ۹۰۰",
                      "top_description_text": "تهران، سعادت‌آباد",
                      "bottom_description_text": "۲ ساعت پیش",
                      "has_chat": True}},
        ]
    }
}

# ── فلوی v2 (فعلی دیوار): posts-v2 → contact_uuid → contact_info_v2 (POST) ──
POSTS_V2_RESPONSE = {"contact": {"contact_uuid": "uuid-gZtQ1"}}
POSTS_V2_NO_CONTACT = {"sections": []}          # uuid ندارد → fallback به v1
PHONE_V2_FOUND = {"widget_list": [
    {"data": {"title": "شمارهٔ موبایل", "value": "۰۹۱۲۱۲۳۴۵۶۷"}}]}   # ارقام فارسی!
PHONE_V2_HIDDEN = {"widget_list": [
    {"data": {"title": "شمارهٔ مخفی‌شده است"}}]}
# ── فلوی v1 قدیمی (پشتیبان) ──
PHONE_V1_FOUND = {
    "widget_list": [
        {"data": {"title": "شماره تماس",
                  "action": {"payload": {"phone_number": 9121234567}}}}
    ]
}


def make_client(responses):
    """کلاینتی که به جای اینترنت، پاسخ‌های داده‌شده را برمی‌گرداند (GET+POST)."""
    cl = DivarClient.__new__(DivarClient)  # بدون خواندن سشن
    cl.session_path = "data/test_session.json"
    cl.token = "fake-jwt-token"
    cl.limiter = MagicMock()  # بدون تاخیر واقعی در تست
    cl.base = "https://api.divar.ir"
    cl.http = MagicMock()
    def _resp(url):
        r = MagicMock()
        r.status_code = responses.get(url, {}).get("status", 200)
        r.json.return_value = responses.get(url, {}).get("json", {})
        r.text = json.dumps(r.json.return_value, ensure_ascii=False)
        return r
    cl.http.get.side_effect = lambda url, **kw: _resp(url)
    cl.http.post.side_effect = lambda url, **kw: _resp(url)
    return cl


class TestParsing(unittest.TestCase):
    def test_search_extract(self):
        cl = make_client({"https://api.divar.ir/v8/web-search/iran":
                          {"json": SEARCH_RESPONSE}})
        posts = cl.search("آپارتمان")
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0]["token"], "gZtQ1")
        self.assertEqual(posts[0]["title"], "آپارتمان ۸۰ متری")
        self.assertTrue(posts[0]["has_chat"])
        self.assertEqual(posts[0]["url"], "https://divar.ir/v/gZtQ1")

    def test_phone_v2_found_persian_digits(self):
        # فلوی فعلی دیوار: uuid → POST v2 → «شمارهٔ موبایل» با ارقام فارسی
        B = "https://api.divar.ir"
        cl = make_client({
            f"{B}/v8/posts-v2/web/gZtQ1": {"json": POSTS_V2_RESPONSE},
            f"{B}/v8/postcontact/web/contact_info_v2/gZtQ1": {"json": PHONE_V2_FOUND},
        })
        res = cl.get_phone("gZtQ1")
        self.assertEqual(res["status"], "found")
        self.assertEqual(res["phone"], "09121234567")  # ۰۹۱۲… → 0912…

    def test_phone_v2_hidden(self):
        B = "https://api.divar.ir"
        cl = make_client({
            f"{B}/v8/posts-v2/web/gZtQ1": {"json": POSTS_V2_RESPONSE},
            f"{B}/v8/postcontact/web/contact_info_v2/gZtQ1": {"json": PHONE_V2_HIDDEN},
        })
        self.assertEqual(cl.get_phone("gZtQ1")["status"], "hidden")

    def test_v1_fallback_when_no_uuid(self):
        # uuid نبود → فلوی قدیمی GET contact_info با Basic
        B = "https://api.divar.ir"
        cl = make_client({
            f"{B}/v8/posts-v2/web/gZtQ1": {"json": POSTS_V2_NO_CONTACT},
            f"{B}/v8/postcontact/web/contact_info/gZtQ1": {"json": PHONE_V1_FOUND},
        })
        res = cl.get_phone("gZtQ1")
        self.assertEqual(res["status"], "found")
        self.assertEqual(res["phone"], "09121234567")

    def test_v1_fallback_when_v2_404(self):
        B = "https://api.divar.ir"
        cl = make_client({
            f"{B}/v8/posts-v2/web/gZtQ1": {"json": POSTS_V2_RESPONSE},
            f"{B}/v8/postcontact/web/contact_info_v2/gZtQ1": {"status": 404},
            f"{B}/v8/postcontact/web/contact_info/gZtQ1": {"json": PHONE_V1_FOUND},
        })
        res = cl.get_phone("gZtQ1")
        self.assertEqual(res["status"], "found")

    def test_removed_post(self):
        B = "https://api.divar.ir"
        cl = make_client({
            f"{B}/v8/posts-v2/web/gone1": {"status": 404},
            f"{B}/v8/postcontact/web/contact_info/gone1": {"status": 404},
        })
        self.assertEqual(cl.get_phone("gone1")["status"], "removed")

    def test_auth_rejected(self):
        B = "https://api.divar.ir"
        cl = make_client({
            f"{B}/v8/posts-v2/web/x": {"json": POSTS_V2_RESPONSE},
            f"{B}/v8/postcontact/web/contact_info_v2/x": {"status": 401},
        })
        with self.assertRaises(DivarAuthError):
            cl.get_phone("x")

    def test_no_token_no_request(self):
        cl = make_client({})
        cl.token = None
        with self.assertRaises(DivarAuthError):
            cl.get_phone("any")

    def test_empty_widgets_stay_error_not_hidden(self):
        from marketing_divar.client import classify_contact_widgets
        self.assertEqual(classify_contact_widgets([])["status"], "error")
        self.assertEqual(classify_contact_widgets(None)["status"], "error")
        self.assertEqual(classify_contact_widgets(
            [{"data": {"title": "چیز دیگر"}}])["status"], "error")
        hid = classify_contact_widgets(
            [{"data": {"title": "شمارهٔ مخفی‌شده است"}}])
        self.assertEqual(hid["status"], "hidden")
        B = "https://api.divar.ir"
        cl = make_client({
            f"{B}/v8/posts-v2/web/gZtQ1": {"json": POSTS_V2_RESPONSE},
            f"{B}/v8/postcontact/web/contact_info_v2/gZtQ1": {"json": {"widget_list": []}},
            f"{B}/v8/postcontact/web/contact_info/gZtQ1": {"json": {"widget_list": []}},
        })
        res = cl.get_phone("gZtQ1")
        self.assertEqual(res["status"], "error")
        self.assertNotEqual(res["status"], "hidden")


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "t.db")
        self.con = connect(self.db_path)

    def test_dedup_and_stats(self):
        post = {"token": "t1", "title": "A", "subtitle": "s", "has_chat": 1,
                "url": "u"}
        self.assertTrue(upsert_lead(self.con, post, "kw", "1"))
        self.assertFalse(upsert_lead(self.con, post, "kw", "1"))  # تکراری
        set_phone(self.con, "t1", {"status": "found", "phone": "0912..."})
        self.con.commit()
        rows = stats(self.con)
        self.assertEqual(rows[0]["total"], 1)
        self.assertEqual(rows[0]["with_phone"], 1)

    def test_export_csv(self):
        post = {"token": "t2", "title": "B", "subtitle": "", "has_chat": 0,
                "url": "u2"}
        upsert_lead(self.con, post, "kw2", "iran")
        set_phone(self.con, "t2", {"status": "hidden"})
        self.con.commit()
        p = os.path.join(self.tmp, "out.csv")
        n_all = export_csv(self.con, p, only_with_phone=False)
        n_ph = export_csv(self.con, p + "2", only_with_phone=True)
        self.assertEqual(n_all, 1)
        self.assertEqual(n_ph, 0)  # hidden → شماره ندارد


if __name__ == "__main__":
    unittest.main(verbosity=2)
