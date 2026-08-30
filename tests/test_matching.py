# -*- coding: utf-8 -*-
"""تست تطبیق کلمه‌کلیدی، بازیابی صف، اسلاگ شهر، سهمیه شماره، اعلان ساخت‌یافته."""

import os
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from marketing_divar.client import city_slug  # noqa: E402
from marketing_divar.db import (connect, lead_exists, reclaim_stuck_processing,  # noqa: E402
                                set_phone, upsert_lead)
from marketing_divar.matching import (consider_new_lead, extract_description,  # noqa: E402
                                      keyword_hits, match_keywords, normalize)
from marketing_divar.notifier import format_alert  # noqa: E402


class TestNormalizeAndMatch(unittest.TestCase):
    def test_persian_variants(self):
        self.assertEqual(normalize("تدريس‌خصوصي"), normalize("تدریس خصوصی"))
        self.assertTrue(keyword_hits("آگهی تدریس‌خصوصی در تهران", "تدریس خصوصی"))
        self.assertTrue(keyword_hits("آپارتمان ۸۰ متری", "اپارتمان"))
        self.assertFalse(keyword_hits("فروش یخچال", "آپارتمان"))

    def test_multi_word_is_phrase(self):
        hits = match_keywords("تدریس ریاضی خصوصی ندارم", ["تدریس خصوصی"])
        self.assertEqual(hits, [])
        hits = match_keywords("کلاس تدریس خصوصی ریاضی", ["تدریس خصوصی"])
        self.assertEqual(hits, ["تدریس خصوصی"])

    def test_extract_description_sections(self):
        detail = {"sections": [{"widgets": [
            {"data": {"text": "توضیح کامل آگهی آپارتمان"}}]}]}
        self.assertIn("آپارتمان", extract_description(detail))


class TestConsiderLead(unittest.TestCase):
    def setUp(self):
        self.con = connect(os.path.join(tempfile.mkdtemp(), "m.db"))

    def test_unmatched_not_stored(self):
        post = {"token": "x1", "title": "فروش یخچال", "subtitle": "",
                "url": "u", "has_chat": 1}
        self.assertFalse(consider_new_lead(
            self.con, None, post, "آپارتمان", "iran", fetch_details=False))
        self.assertFalse(lead_exists(self.con, "x1"))

    def test_matched_stored_once(self):
        post = {"token": "x2", "title": "آپارتمان ۸۰ متری", "subtitle": "",
                "url": "u", "has_chat": 1}
        self.assertTrue(consider_new_lead(
            self.con, None, post, "آپارتمان", "iran", fetch_details=False))
        self.assertFalse(consider_new_lead(
            self.con, None, post, "آپارتمان", "iran", fetch_details=False))
        self.assertTrue(lead_exists(self.con, "x2"))


class TestReclaimAndCity(unittest.TestCase):
    def test_reclaim_processing(self):
        con = connect(os.path.join(tempfile.mkdtemp(), "r.db"))
        upsert_lead(con, {"token": "t1", "title": "A", "subtitle": "",
                          "url": "u", "has_chat": 1}, "kw", "iran")
        con.execute("UPDATE leads SET phone_status='processing' WHERE token='t1'")
        con.commit()
        n = reclaim_stuck_processing(con)
        self.assertEqual(n, 1)
        st = con.execute("SELECT phone_status FROM leads WHERE token='t1'").fetchone()
        self.assertEqual(st["phone_status"], "pending")

    def test_city_slug(self):
        self.assertEqual(city_slug(None), "iran")
        self.assertEqual(city_slug([1]), "tehran")
        self.assertEqual(city_slug(["3"]), "mashhad")
        self.assertEqual(city_slug(["shiraz"]), "shiraz")
        self.assertEqual(city_slug([999]), "iran")


class TestPhoneLimiter(unittest.TestCase):
    def test_get_phone_waits_phone_kind(self):
        from test_offline import PHONE_V2_FOUND, POSTS_V2_RESPONSE, make_client
        B = "https://api.divar.ir"
        cl = make_client({
            f"{B}/v8/posts-v2/web/gZtQ1": {"json": POSTS_V2_RESPONSE},
            f"{B}/v8/postcontact/web/contact_info_v2/gZtQ1": {"json": PHONE_V2_FOUND},
        })
        cl.limiter = MagicMock()
        cl.get_phone("gZtQ1")
        cl.limiter.wait.assert_any_call("phone")

    def test_phone_min_interval(self):
        from marketing_divar.rate import RateLimiter
        from test_offline import PHONE_V2_FOUND, POSTS_V2_RESPONSE, make_client
        B = "https://api.divar.ir"
        cl = make_client({
            f"{B}/v8/posts-v2/web/gZtQ1": {"json": POSTS_V2_RESPONSE},
            f"{B}/v8/postcontact/web/contact_info_v2/gZtQ1": {"json": PHONE_V2_FOUND},
        })
        cl.limiter = RateLimiter(phone_delay=0.05, search_delay=0, jitter=0)
        t0 = time.monotonic()
        cl.get_phone("gZtQ1")
        cl.get_phone("gZtQ1")
        self.assertGreaterEqual(time.monotonic() - t0, 0.05)


class TestAlertFormat(unittest.TestCase):
    def test_structured_fields(self):
        txt = format_alert("کپچا آمد", account="ac1", problem="captcha",
                           operation="contact", action="آزادسازی ac1")
        self.assertIn("اکانت: ac1", txt)
        self.assertIn("مشکل: captcha", txt)
        self.assertIn("عملیات: contact", txt)
        self.assertIn("اقدام لازم", txt)
        self.assertIn("زمان:", txt)


class TestChatStatusOnHidden(unittest.TestCase):
    def test_hidden_marks_chat_available(self):
        con = connect(os.path.join(tempfile.mkdtemp(), "c.db"))
        upsert_lead(con, {"token": "h1", "title": "A", "subtitle": "",
                          "url": "u", "has_chat": 1}, "kw", "iran")
        set_phone(con, "h1", {"status": "hidden"})
        con.commit()
        row = con.execute("SELECT chat_status FROM leads WHERE token='h1'").fetchone()
        self.assertEqual(row["chat_status"], "available")


if __name__ == "__main__":
    unittest.main()
