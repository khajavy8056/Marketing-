# -*- coding: utf-8 -*-
"""آزادسازی: با همان اکانت به دیوار بزن؛ اگر پازل رفته بود خودکار باز شود."""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from marketing_divar.accounts import AccountManager  # noqa: E402
from marketing_divar.client import DivarClient  # noqa: E402
from marketing_divar.config import DEFAULTS  # noqa: E402
from marketing_divar.rate import RateLimiter  # noqa: E402
from marketing_divar.unlock import (  # noqa: E402
    confirm_captcha_phone, next_probe_wait, try_release_account)
from mock_divar import MockDivar, start_mock  # noqa: E402


def _acct(root, name="ac1"):
    d = os.path.join(root, "accounts", name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "session.json"), "w", encoding="utf-8") as f:
        json.dump({"phone": "09120000000", "token": f"tok-{name}"}, f)
    return os.path.join(root, "accounts")


class TestProbeGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        MockDivar.reset()
        self.srv = start_mock()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.acc = _acct(self.tmp, "ac1")

    def tearDown(self):
        self.srv.shutdown()

    def _cl(self, name="ac1"):
        return DivarClient(
            session_path=os.path.join(self.acc, name, "session.json"),
            base_url=self.base,
            limiter=RateLimiter(phone_delay=0, search_delay=0, jitter=0))

    def test_probe_clear_when_not_captcha(self):
        res = self._cl().probe_gate()
        self.assertTrue(res["ok"])
        self.assertEqual(res["state"], "clear")

    def test_probe_captcha_then_clear_after_phone_solve(self):
        MockDivar.captcha_after = {"ac1": 0}
        res = self._cl().probe_gate()
        self.assertFalse(res["ok"])
        self.assertEqual(res["state"], "captcha")
        # کاربر روی گوشی حل کرد
        MockDivar.released.add("ac1")
        res = self._cl().probe_gate()
        self.assertTrue(res["ok"])
        self.assertEqual(res["state"], "clear")

    def test_try_release_auto_opens(self):
        MockDivar.captcha_after = {"ac1": 0}
        mgr = AccountManager(DEFAULTS, self.acc)
        mgr.set_status("ac1", "captcha", note="blocked")
        r = try_release_account(mgr, "ac1", base_url=self.base)
        self.assertFalse(r["cleared"])
        self.assertEqual(mgr.snapshot(os.path.join(self.tmp, "x.db"))[0]["status"], "captcha")
        MockDivar.released.add("ac1")
        r = try_release_account(mgr, "ac1", base_url=self.base, reason="auto-probe")
        self.assertTrue(r["cleared"])
        self.assertEqual(mgr.snapshot(os.path.join(self.tmp, "x.db"))[0]["status"], "active")

    def test_backoff_is_not_half_hour_first(self):
        self.assertLessEqual(next_probe_wait(60), 180)
        self.assertGreaterEqual(next_probe_wait(40 * 60), 10 * 60)

    def test_confirm_cleared_gets_one_queued_phone(self):
        from marketing_divar.db import connect, upsert_lead
        db = os.path.join(self.tmp, "leads.db")
        con = connect(db)
        upsert_lead(con, {"token": "ph1aaaa", "title": "آگهی",
                          "subtitle": "", "url": "https://divar.ir/v/ph1aaaa",
                          "has_chat": True}, "kw", "1")
        con.commit()
        con.close()
        mgr = AccountManager(DEFAULTS, self.acc)
        mgr.set_status("ac1", "captcha", note="blocked")
        r = confirm_captcha_phone(mgr, "ac1", db, base_url=self.base)
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["cleared"], r)
        self.assertTrue(r["phone_tried"], r)
        self.assertEqual(r.get("status"), "found")
        self.assertTrue(str(r.get("phone") or "").startswith("0912"))
        self.assertEqual(
            mgr.snapshot(db)[0]["status"], "active")
        con = connect(db)
        row = con.execute(
            "SELECT phone_status, phone FROM leads WHERE token='ph1aaaa'"
        ).fetchone()
        con.close()
        self.assertEqual(row["phone_status"], "found")
        self.assertTrue(str(row["phone"]).startswith("0912"))

    def test_confirm_still_captcha_keeps_queue(self):
        from marketing_divar.db import connect, upsert_lead
        db = os.path.join(self.tmp, "leads2.db")
        con = connect(db)
        upsert_lead(con, {"token": "ph2bbbb", "title": "آگهی",
                          "subtitle": "", "url": "u",
                          "has_chat": True}, "kw", "1")
        con.commit()
        con.close()
        MockDivar.captcha_after = {"ac1": 0}
        mgr = AccountManager(DEFAULTS, self.acc)
        mgr.set_status("ac1", "captcha")
        r = confirm_captcha_phone(mgr, "ac1", db, base_url=self.base)
        self.assertFalse(r["cleared"], r)
        self.assertTrue(r["phone_tried"], r)
        self.assertEqual(r.get("state"), "captcha")
        self.assertEqual(mgr.snapshot(db)[0]["status"], "captcha")
        con = connect(db)
        st = con.execute(
            "SELECT phone_status FROM leads WHERE token='ph2bbbb'"
        ).fetchone()["phone_status"]
        con.close()
        self.assertEqual(st, "pending")


if __name__ == "__main__":
    unittest.main(verbosity=2)
