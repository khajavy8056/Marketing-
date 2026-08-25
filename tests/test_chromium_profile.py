# -*- coding: utf-8 -*-
"""پروفایل پایدار Chromium — بدون تزریق کوکی."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from marketing_divar.chromium_profile import (  # noqa: E402
    HOME_URL, cookies_look_logged_in, harvest_to_session, load_meta,
    profile_ready, safe_name, save_meta, snapshot_fields)
from marketing_divar.config import DEFAULTS  # noqa: E402
from marketing_divar.accounts import AccountManager  # noqa: E402


class TestSafeName(unittest.TestCase):
    def test_persian_and_spaces(self):
        self.assertEqual(safe_name("محمد تهران 01"), "محمد-تهران-01")
        self.assertRaises(ValueError, safe_name, "  ")


class TestMetaAndReady(unittest.TestCase):
    def test_save_and_ready_flag(self):
        d = tempfile.mkdtemp()
        save_meta(d, "acc1", {"profile_ready": False, "phone": "09120000000"})
        self.assertFalse(profile_ready(d, "acc1"))
        rec = save_meta(d, "acc1", {"profile_ready": True,
                                    "saved_at": "2026-08-26"})
        self.assertTrue(profile_ready(d, "acc1"))
        self.assertEqual(rec["home_url"], HOME_URL)
        self.assertTrue((Path(d) / "acc1" / "account.json").exists())
        snap = snapshot_fields(d, "acc1")
        self.assertTrue(snap["profile_ready"])
        self.assertEqual(snap["profile_saved_at"], "2026-08-26")

    def test_cookies_login_hint(self):
        self.assertFalse(cookies_look_logged_in([]))
        self.assertFalse(cookies_look_logged_in(
            [{"name": "foo", "domain": ".divar.ir"}]))
        self.assertTrue(cookies_look_logged_in(
            [{"name": "sRefreshToken", "value": "R", "domain": ".divar.ir"}]))

    def test_harvest_writes_session(self):
        d = tempfile.mkdtemp()
        save_meta(d, "acc1", {"phone": "09121112222"})
        harvest_to_session(d, "acc1", [
            {"name": "sRefreshToken", "value": "RR", "domain": ".divar.ir"},
            {"name": "sAccessToken", "value": "AA", "domain": ".divar.ir"},
            {"name": "sFrontToken", "value": "FF", "domain": ".divar.ir"},
            {"name": "skip", "value": "x", "domain": ".google.com"},
        ])
        data = json.loads((Path(d) / "acc1" / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(data["cookies"]["sRefreshToken"], "RR")
        self.assertNotIn("skip", data["cookies"])
        from marketing_divar.auth_session import session_is_complete
        self.assertTrue(session_is_complete(str(Path(d) / "acc1" / "session.json")))

    def test_manager_lists_profile_without_token(self):
        d = tempfile.mkdtemp()
        save_meta(d, "only-profile", {"profile_ready": True})
        (Path(d) / "only-profile" / "chromium").mkdir(parents=True)
        m = AccountManager(DEFAULTS, d)
        db = os.path.join(d, "x.db")
        from marketing_divar.db import connect
        connect(db).close()
        names = [a["name"] for a in m.snapshot(db)]
        self.assertIn("only-profile", names)
        one = next(a for a in m.snapshot(db) if a["name"] == "only-profile")
        self.assertTrue(one["profile_ready"])
        self.assertTrue(m.has_full_login("only-profile"))


class TestCreateOpenMocked(unittest.TestCase):
    def test_create_and_open_uses_tehran(self):
        from marketing_divar import chromium_profile as cp
        d = tempfile.mkdtemp()
        with mock.patch.object(cp, "open_profile",
                               return_value={"ok": True, "url": HOME_URL,
                                             "message": "opened"}) as op:
            res = cp.create_and_open(d, "ali tehran 02", "09120000000")
        self.assertTrue(res["ok"])
        op.assert_called_once()
        args, kwargs = op.call_args
        self.assertEqual(args[2], HOME_URL)
        self.assertTrue((Path(d) / "ali-tehran-02" / "chromium").is_dir())
        self.assertEqual(load_meta(d, "ali-tehran-02").get("phone"), "09120000000")


if __name__ == "__main__":
    unittest.main(verbosity=2)
