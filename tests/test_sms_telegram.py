# -*- coding: utf-8 -*-
"""ملی‌پیامک رسمی + فرمان‌های ربات تلگرام — بدون شبکه واقعی."""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from marketing_divar.sms import (  # noqa: E402
    interpret_meli, maybe_send_for_lead, send_melipayamak)
from marketing_divar.telegram_bot import handle_command  # noqa: E402
from marketing_divar.db import connect, upsert_lead  # noqa: E402


class FakeResp:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class TestMeliPayamak(unittest.TestCase):
    def test_interpret_recid(self):
        ok, msg = interpret_meli({"Value": "8512345678", "RetStatus": 1})
        self.assertTrue(ok)
        self.assertIn("recid", msg)

    def test_interpret_error(self):
        ok, _ = interpret_meli({"Value": "11", "StrRetStatus": "InvalidUser"})
        self.assertFalse(ok)

    def test_send_uses_official_url(self):
        seen = {}

        def poster(url, data, timeout=20):
            seen["url"] = url
            seen["data"] = data
            return FakeResp({"Value": "9000000001", "RetStatus": 1})

        r = send_melipayamak("u", "p", "09120000000", "3000", "سلام",
                             http_post=poster)
        self.assertTrue(r["ok"])
        self.assertIn("rest.payamak-panel.com", seen["url"])
        self.assertEqual(seen["data"]["username"], "u")
        self.assertEqual(seen["data"]["to"], "09120000000")

    def test_auto_off_by_default(self):
        self.assertIsNone(maybe_send_for_lead(
            {"sms_provider": "melipayamak"},
            {"phone": "09120000000", "title": "x"}, "سلام {title}"))

    def test_auto_on_sends(self):
        def poster(url, data, timeout=20):
            return FakeResp({"Value": "9000000002"})

        r = maybe_send_for_lead({
            "sms_auto_on_new": True,
            "sms_provider": "melipayamak",
            "sms_username": "u",
            "sms_password": "p",
            "sms_line_number": "3000",
        }, {"phone": "09121112233", "title": "ویلا"}, "سلام {title}",
            http_post=poster)
        self.assertTrue(r and r["ok"])


class TestTelegramCommands(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "t.db")
        con = connect(self.db)
        upsert_lead(con, {"token": "t1", "title": "ویلا شمال",
                          "url": "https://divar.ir/v/t1", "has_chat": True},
                    "ویلا", "iran")
        con.execute("UPDATE leads SET phone=?, phone_status='found' WHERE token='t1'",
                    ("09145822150",))
        con.commit()
        con.close()
        self.cfg = {"ip_daily_limit": 240}

    def test_help_and_status(self):
        h = handle_command("/help", self.db, self.cfg)
        self.assertIn("/status", h)
        self.assertIn("/leads", h)
        st = handle_command("/status", self.db, self.cfg)
        self.assertIn("خواجوی لید", st)
        self.assertIn("سقف IP", st)

    def test_leads_today(self):
        t = handle_command("/leads", self.db, self.cfg)
        self.assertIn("09145822150", t)

    def test_unknown(self):
        self.assertIn("ناشناخته", handle_command("/nope", self.db, self.cfg))


if __name__ == "__main__":
    unittest.main(verbosity=2)
