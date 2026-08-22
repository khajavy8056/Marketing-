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

PHONE_FOUND_RESPONSE = {
    "widget_list": [
        {"data": {"title": "شماره تماس",
                  "action": {"payload": {"phone_number": 9121234567}}}}
    ]
}

PHONE_HIDDEN_RESPONSE = {
    "widget_list": [{"data": {"title": "شماره مخفی شده است"}}]
}


def make_client(responses):
    """کلاینتی که به جای اینترنت، پاسخ‌های داده‌شده را برمی‌گرداند."""
    cl = DivarClient.__new__(DivarClient)  # بدون خواندن سشن
    cl.session_path = "data/test_session.json"
    cl.token = "fake-jwt-token"
    cl.limiter = MagicMock()  # بدون تاخیر واقعی در تست
    cl.base = "https://api.divar.ir"
    cl.http = MagicMock()
    def get(url, **kw):
        r = MagicMock()
        r.status_code = responses.get(url, {}).get("status", 200)
        r.json.return_value = responses.get(url, {}).get("json", {})
        r.text = json.dumps(r.json.return_value, ensure_ascii=False)
        return r
    cl.http.get.side_effect = get
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

    def test_phone_found_normalized(self):
        # دیوار گاهی 9121234567 می‌دهد → باید 09121234567 ذخیره شود
        cl = make_client({"https://api.divar.ir/v8/postcontact/web/contact_info/gZtQ1":
                          {"json": PHONE_FOUND_RESPONSE}})
        res = cl.get_phone("gZtQ1")
        self.assertEqual(res["status"], "found")
        self.assertEqual(res["phone"], "09121234567")

    def test_phone_hidden(self):
        cl = make_client({"https://api.divar.ir/v8/postcontact/web/contact_info/kYw3A":
                          {"json": PHONE_HIDDEN_RESPONSE}})
        res = cl.get_phone("kYw3A")
        self.assertEqual(res["status"], "hidden")

    def test_auth_rejected(self):
        cl = make_client({"https://api.divar.ir/v8/postcontact/web/contact_info/x":
                          {"status": 401}})
        with self.assertRaises(DivarAuthError):
            cl.get_phone("x")

    def test_no_token_no_request(self):
        cl = make_client({})
        cl.token = None
        with self.assertRaises(DivarAuthError):
            cl.get_phone("any")


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
