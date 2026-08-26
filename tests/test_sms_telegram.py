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
    interpret_meli, maybe_send_for_lead, normalize_ir_phone,
    send_for_lead, send_melipayamak)
from marketing_divar.telegram_bot import (  # noqa: E402
    found_alert_text, handle_command, handle_update)
from marketing_divar.notifier import (  # noqa: E402
    bale_configured, notify, rubika_configured, send_bale, send_rubika)
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

    def test_normalize_phone(self):
        self.assertEqual(normalize_ir_phone("+989145822150"), "09145822150")
        self.assertEqual(normalize_ir_phone("9145822150"), "09145822150")

    def test_auto_off_by_default(self):
        self.assertIsNone(maybe_send_for_lead(
            {"sms_provider": "melipayamak"},
            {"phone": "09120000000", "title": "x"}, "سلام {title}"))

    def test_manual_send_uses_template(self):
        seen = {}

        def poster(url, data, timeout=20):
            seen["text"] = data["text"]
            seen["to"] = data["to"]
            return FakeResp({"Value": "9000000003"})

        r = send_for_lead({
            "sms_provider": "melipayamak",
            "sms_username": "u", "sms_password": "p",
            "sms_line_number": "3000",
        }, {"phone": "+989121112233", "title": "ویلا"}, "سلام {title}",
            http_post=poster)
        self.assertTrue(r["ok"])
        self.assertEqual(seen["to"], "09121112233")
        self.assertIn("ویلا", seen["text"])

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
        self.assertIn("مارکتینگ دیوار", st)
        self.assertIn("سقف IP", st)

    def test_leads_today(self):
        t = handle_command("/leads", self.db, self.cfg)
        self.assertIn("09145822150", t)

    def test_unknown(self):
        self.assertIn("ناشناخته", handle_command("/nope", self.db, self.cfg))

    def test_bottom_buttons(self):
        self.assertIn("سقف IP", handle_command("📊 گزارش امروز", self.db, self.cfg))
        self.assertIn("09145822150", handle_command("سرنخ‌های امروز", self.db, self.cfg))
        self.assertIn("09145822150", handle_command("📋 همه شماره‌ها", self.db, self.cfg))
        self.assertIn("آلارم", handle_command("🚨 آلارم‌های مهم", self.db, self.cfg))
        out = handle_update("⬇️ خروجی اکسل", self.db, self.cfg)
        self.assertTrue(out["document"])
        self.assertIn("تاریخ‌ساعت استخراج شماره", out["document"].decode("utf-8-sig"))
        self.assertIn("09145822150", out["document"].decode("utf-8-sig"))

    def test_found_alert_counts(self):
        t = found_alert_text("ویلا", "09145822150", "2026-08-23 18:00:00", 4)
        self.assertIn("سرنخ جدید پیدا شد", t)
        self.assertIn("شماره امروز تا الان: 4", t)
        self.assertIn("2026-08-23 18:00:00", t)


class TestBaleRubika(unittest.TestCase):
    def test_configured(self):
        cfg = {"notify": {"bale_bot_token": "t", "bale_chat_id": "1",
                          "rubika_bot_token": "r", "rubika_chat_id": "2"}}
        self.assertTrue(bale_configured(cfg))
        self.assertTrue(rubika_configured(cfg))
        self.assertFalse(bale_configured({"notify": {}}))
        self.assertFalse(bale_configured({
            "notify": {"bale_bot_token": "t", "bale_chat_id": "1",
                       "bale_enabled": False}}))

    def test_send_official_urls(self):
        seen = []

        class R:
            status_code = 200
            def json(self):
                return {"ok": True, "status": "OK"}

        def poster(url, json=None, data=None, files=None, params=None,
                   timeout=12, headers=None, proxies=None, **kw):
            seen.append((url, json))
            return R()

        import marketing_divar.notifier as n
        old = n.requests
        class Fake:
            post = staticmethod(poster)
        n.requests = Fake
        try:
            cfg = {"notify": {"bale_bot_token": "BT", "bale_chat_id": "9",
                              "rubika_bot_token": "RT", "rubika_chat_id": "8"}}
            self.assertTrue(send_bale(cfg, "سلام"))
            self.assertTrue(send_rubika(cfg, "سلام"))
            notify(cfg, "آزمایش", important=False)
        finally:
            n.requests = old
        urls = [u for u, _ in seen]
        self.assertTrue(any("tapi.bale.ai/botBT/sendMessage" in u for u in urls))
        self.assertTrue(any("botapi.rubika.ir/v3/RT/sendMessage" in u for u in urls))

    def test_channel_probe_uses_getme(self):
        seen = []

        class R:
            status_code = 200
            def json(self):
                return {"ok": True, "status": "OK", "result": {"username": "x"}}

        def poster(url, json=None, data=None, files=None, params=None,
                   timeout=12, headers=None, proxies=None):
            seen.append(url)
            return R()

        import marketing_divar.notifier as n
        old = n.requests
        class Fake:
            post = staticmethod(poster)
        n.requests = Fake
        try:
            from marketing_divar.notifier import test_channel
            cfg = {"notify": {"bale_bot_token": "BT", "bale_chat_id": "9",
                              "bale_enabled": True}}
            r = test_channel(cfg, "bale")
            self.assertTrue(r["ok"], r)
            self.assertTrue(any("tapi.bale.ai/botBT/getMe" in u for u in seen))
            self.assertTrue(any("sendMessage" in u for u in seen))
        finally:
            n.requests = old


if __name__ == "__main__":
    unittest.main(verbosity=2)
