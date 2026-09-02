# -*- coding: utf-8 -*-
"""صف شماره نباید به‌خاطر پاسخ خالی «فقط چت» شود؛ ۴۰۳ باید پاپ‌آپ آزادسازی بدهد."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from marketing_divar.client import DivarBlockedError  # noqa: E402
from marketing_divar.config import DEFAULTS  # noqa: E402
from marketing_divar.db import connect, pending_phone, upsert_lead  # noqa: E402
from marketing_divar.monitor import Monitor  # noqa: E402
from marketing_divar.notifier import send_telegram, telegram_bases  # noqa: E402


def _acct(root, name="ac1"):
    d = os.path.join(root, "accounts", name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "session.json"), "w", encoding="utf-8") as f:
        json.dump({"phone": "09120000000", "token": f"tok-{name}"}, f)
    return os.path.join(root, "accounts")


class TestEmptyContactStaysPending(unittest.TestCase):
    def test_fetch_error_keeps_pending(self):
        tmp = tempfile.mkdtemp()
        db = os.path.join(tmp, "t.db")
        con = connect(db)
        upsert_lead(con, {"token": "e1", "title": "آگهی شماره", "subtitle": "",
                          "url": "u", "has_chat": 1}, "kw", "iran")
        con.commit()
        con.close()
        acc = _acct(tmp)
        cfg = dict(DEFAULTS)
        cfg.update({"phone_delay_sec": 0, "jitter_sec": 0, "ip_daily_limit": 50})
        mon = Monitor(cfg, [{"keyword": "kw"}], db_path=db, accounts_dir=acc,
                      interactive=False)
        fake = MagicMock()
        fake.get_phone.return_value = {"status": "error", "message": "خالی"}
        mon.client_for = lambda name: fake
        self.assertEqual(mon._fetch_one(), "done")
        con = connect(db)
        row = con.execute("SELECT phone_status FROM leads WHERE token='e1'").fetchone()
        self.assertEqual(row["phone_status"], "pending")
        self.assertEqual(len(pending_phone(con)), 1)
        con.close()

    def test_second_error_gates_captcha(self):
        tmp = tempfile.mkdtemp()
        db = os.path.join(tmp, "t.db")
        con = connect(db)
        upsert_lead(con, {"token": "e2", "title": "آگهی", "subtitle": "",
                          "url": "u", "has_chat": 1}, "kw", "iran")
        upsert_lead(con, {"token": "e3", "title": "آگهی۲", "subtitle": "",
                          "url": "u", "has_chat": 1}, "kw", "iran")
        con.commit()
        con.close()
        acc = _acct(tmp)
        cfg = dict(DEFAULTS)
        cfg.update({"phone_delay_sec": 0, "jitter_sec": 0})
        mon = Monitor(cfg, [{"keyword": "kw"}], db_path=db, accounts_dir=acc,
                      interactive=False)
        fake = MagicMock()
        # خطای خالی کپچا نیست — اکانت نباید قفل شود
        fake.get_phone.return_value = {"status": "error", "message": "خالی"}
        mon.client_for = lambda name: fake
        self.assertEqual(mon._fetch_one(), "done")
        self.assertEqual(mon._fetch_one(), "done")
        st = next(a for a in mon.mgr.snapshot(db) if a["name"] == "ac1")
        self.assertNotEqual(st["status"], "captcha")
        # کپچا واقعی بعد از چند خطای بلاک
        fake.get_phone.return_value = {"status": "error", "message": "captcha required"}
        for _ in range(3):
            r = mon._fetch_one()
            if r == "wait":
                break
        st = next(a for a in mon.mgr.snapshot(db) if a["name"] == "ac1")
        self.assertEqual(st["status"], "captcha")

    def test_403_without_captcha_word_still_gates(self):
        tmp = tempfile.mkdtemp()
        db = os.path.join(tmp, "t.db")
        con = connect(db)
        upsert_lead(con, {"token": "e4", "title": "آگهی", "subtitle": "",
                          "url": "u", "has_chat": 1}, "kw", "iran")
        con.commit()
        con.close()
        acc = _acct(tmp)
        mon = Monitor(dict(DEFAULTS), [{"keyword": "kw"}], db_path=db,
                      accounts_dir=acc, interactive=False)
        fake = MagicMock()
        fake.get_phone.side_effect = DivarBlockedError("دسترسی ممنوع (403)", 403, "forbidden")
        mon.client_for = lambda name: fake
        self.assertEqual(mon._fetch_one(), "wait")
        st = next(a for a in mon.mgr.snapshot(db) if a["name"] == "ac1")
        self.assertEqual(st["status"], "captcha")
        con = connect(db)
        row = con.execute("SELECT phone_status FROM leads WHERE token='e4'").fetchone()
        self.assertEqual(row["phone_status"], "pending")
        con.close()


class TestTelegramPaths(unittest.TestCase):
    def test_custom_base_first(self):
        cfg = {"notify": {"telegram_api_base": "https://tg.example.com",
                          "telegram_bot_token": "1:AA",
                          "telegram_chat_id": "9"}}
        self.assertEqual(telegram_bases(cfg)[0], "https://tg.example.com")
        called = []

        class R:
            status_code = 200
            text = '{"ok":true}'

            def json(self):
                return {"ok": True}

        def fake_post(url, **kw):
            called.append(url)
            return R()

        with patch("marketing_divar.notifier.requests.post", fake_post):
            self.assertTrue(send_telegram(cfg, "hi"))
        self.assertTrue(any("tg.example.com" in u for u in called))

    def test_failure_does_not_raise(self):
        cfg = {"notify": {"telegram_bot_token": "1:AA", "telegram_chat_id": "9"}}

        def boom(*a, **k):
            raise OSError("filtered")

        with patch("marketing_divar.notifier.requests.post", boom):
            self.assertFalse(send_telegram(cfg, "hi"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
