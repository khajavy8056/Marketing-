# -*- coding: utf-8 -*-
"""نشست ورود برنامه + به‌خاطر سپردن."""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


class TestLicenseSession(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        os.environ["DIVAR_DATA_DIR"] = self._tmp

    def test_sign_verify_and_remember(self):
        from marketing_divar import license_session as ls
        with patch.object(ls, "_data_dir", lambda: Path(self._tmp)):
            tok = ls.sign_payload({"u": "demo", "n": "علی دمو", "p": "demo",
                                   "days_left": 17, "exp": int(time.time()) + 86400})
            data = ls.verify_payload(tok)
            self.assertIsNotNone(data)
            self.assertEqual(data["u"], "demo")
            self.assertIsNone(ls.verify_payload("bad.token"))
            self.assertIsNone(ls.verify_payload(""))
            ls.save_remember("demo", "demo123")
            rem = ls.load_remember()
            self.assertEqual(rem["username"], "demo")
            self.assertEqual(rem["password"], "demo123")
            ls.clear_remember()
            self.assertFalse(ls.load_remember())
        self.assertEqual(ls.span_days("2026-08-01", "2026-09-15", 17), 45)

    def test_public_paths(self):
        from marketing_divar.license_session import is_public
        self.assertTrue(is_public("/"))
        self.assertTrue(is_public("/logo.png"))
        self.assertTrue(is_public("/api/license/login"))
        self.assertTrue(is_public("/api/license/me"))
        self.assertFalse(is_public("/api/status"))
        self.assertFalse(is_public("/api/accounts"))


class TestContactDispatch(unittest.TestCase):
    def test_html_phone_hidden_removed(self):
        from marketing_divar.contact import classify_listing_html, get_contact, parse_visible_phone
        self.assertEqual(parse_visible_phone("تماس ۰۹۱۲۳۴۵۶۷۸۹ بزنید"), "09123456789")
        found = classify_listing_html("شماره 09121112233 در آگهی", "sheypoor")
        self.assertEqual(found["status"], "found")
        hid = classify_listing_html("فقط چت با فروشنده", "ring")
        self.assertEqual(hid["status"], "hidden")
        gone = classify_listing_html("این آگهی حذف شده است", "divar")
        self.assertEqual(gone["status"], "removed")

        def reveal(url, plat, nid):
            self.assertEqual(plat, "sheypoor")
            self.assertEqual(nid, "99")
            return {"status": "found", "phone": "09120000000"}

        r = get_contact("sheypoor:99", reveal_fn=reveal,
                        url="https://www.sheypoor.com/v/x-99.html")
        self.assertEqual(r["status"], "found")
        self.assertEqual(r["phone"], "09120000000")

    def test_divar_uses_client_get_phone(self):
        from marketing_divar.contact import get_contact

        class C:
            def get_phone(self, token):
                self.seen = token
                return {"status": "found", "phone": "09125550000"}

        c = C()
        r = get_contact("abcTOK", client=c)
        self.assertEqual(c.seen, "abcTOK")
        self.assertEqual(r["phone"], "09125550000")
        self.assertEqual(r["platform"], "divar")


class TestMatchingOtherPlatforms(unittest.TestCase):
    def test_sheypoor_skips_divar_get_post(self):
        from marketing_divar.db import connect, lead_exists
        from marketing_divar.matching import consider_new_lead

        class Boom:
            def get_post(self, token):
                raise AssertionError("should not fetch divar post for sheypoor")

        con = connect(os.path.join(tempfile.mkdtemp(), "m.db"))
        post = {"token": "sheypoor:55555", "title": "آیفون ۱۳ پرومکس",
                "url": "https://www.sheypoor.com/v/iphone-55555.html",
                "platform": "sheypoor", "native_id": "55555"}
        self.assertTrue(consider_new_lead(
            con, Boom(), post, "آیفون", "iran", fetch_details=True))
        self.assertTrue(lead_exists(con, "sheypoor:55555"))


class TestAccountRotate(unittest.TestCase):
    def test_pick_skips_last(self):
        from marketing_divar.accounts import AccountManager
        from marketing_divar.config import DEFAULTS
        root = tempfile.mkdtemp()
        for name in ("a1", "a2"):
            d = os.path.join(root, name)
            os.makedirs(d)
            with open(os.path.join(d, "session.json"), "w") as fh:
                fh.write('{"token":"t-%s"}' % name)
        mgr = AccountManager(dict(DEFAULTS), root)
        first = mgr.pick(os.path.join(tempfile.mkdtemp(), "q.db"))
        self.assertIn(first, ("a1", "a2"))
        second = mgr.pick(os.path.join(tempfile.mkdtemp(), "q2.db"), skip=first)
        self.assertNotEqual(second, first)


class TestChatLabels(unittest.TestCase):
    def test_platform_labels(self):
        from marketing_divar.chat_browser import _chat_click_labels, _js_send
        self.assertIn("پیام به فروشنده", _chat_click_labels("sheypoor"))
        js = _js_send("سلام", "sheypoor")
        self.assertIn("پیام به فروشنده", js)


if __name__ == "__main__":
    unittest.main()
