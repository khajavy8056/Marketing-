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
        self.assertTrue(cookies_look_logged_in(
            [{"name": "sAccessToken", "value": "", "host_key": ".divar.ir"}]))
        self.assertTrue(cookies_look_logged_in(
            [{"name": "st-last-access-token", "value": "x",
              "domain": ".divar.ir"}]))

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

    def test_open_prepares_named_profile_and_user_data_dir(self):
        from marketing_divar import chromium_profile as cp
        d = tempfile.mkdtemp()
        cmds = []

        class Proc:
            pid = 9
            def poll(self):
                return None

        def popen(cmd, **kw):
            cmds.append(cmd)
            return Proc()

        with mock.patch.object(cp.subprocess, "Popen", side_effect=popen), \
             mock.patch.object(cp, "_cdp_alive", return_value=True), \
             mock.patch("marketing_divar.app_chromium.is_ready", return_value=True), \
             mock.patch("marketing_divar.app_chromium.ensure_installed"), \
             mock.patch("marketing_divar.app_chromium.apply_browser_env"), \
             mock.patch("marketing_divar.app_chromium.executable_path",
                        return_value="/opt/app/chrome"):
            res = cp.open_profile(d, "acc1", HOME_URL)
        self.assertTrue(res["ok"])
        cmd = cmds[0]
        joined = " ".join(cmd)
        self.assertIn("--user-data-dir=", joined)
        self.assertIn("--profile-directory=Default", cmd)
        self.assertNotIn("--new-window", cmd)
        udd = [x.split("=", 1)[1] for x in cmd if x.startswith("--user-data-dir=")][0]
        self.assertTrue(os.path.isabs(udd))
        self.assertIn("acc1", udd.replace("\\", "/"))
        prefs = Path(d) / "acc1" / "chromium" / "Default" / "Preferences"
        self.assertTrue(prefs.exists())
        data = json.loads(prefs.read_text(encoding="utf-8"))
        self.assertEqual(data["profile"]["name"], "acc1")

    def test_persian_name_uses_ascii_user_data_dir(self):
        from marketing_divar import chromium_profile as cp
        d = tempfile.mkdtemp()
        p = cp.chromium_dir(d, "محمد تهران 01")
        self.assertTrue(all(ord(c) < 128 for c in p.name))
        self.assertIn("chromium-profiles", str(p).replace("\\", "/"))
        logical = Path(d) / "محمد-تهران-01" / "chromium"
        self.assertNotEqual(p.resolve(), logical)


def _write_cookie_db(path, rows):
    import sqlite3
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE cookies (name TEXT, host_key TEXT, value TEXT)")
    con.executemany("INSERT INTO cookies VALUES (?,?,?)", rows)
    con.commit()
    con.close()


class TestSqliteSave(unittest.TestCase):
    def test_disk_cookies_save_without_cdp(self):
        from marketing_divar import chromium_profile as cp
        d = tempfile.mkdtemp()
        save_meta(d, "acc1", {"phone": "09120000000"})
        prof = cp.chromium_dir(d, "acc1")
        _write_cookie_db(
            prof / "Default" / "Network" / "Cookies",
            [("sRefreshToken", ".divar.ir", ""),
             ("sAccessToken", ".divar.ir", ""),
             ("sid", ".google.com", "x")])
        with mock.patch.object(cp, "is_open", return_value=False), \
             mock.patch.object(cp, "_cdp_alive", return_value=False), \
             mock.patch.object(cp, "_cookies_from_live") as live, \
             mock.patch.object(cp, "close_live") as cl:
            res = cp.save_profile(d, "acc1")
        self.assertTrue(res["ok"], res)
        self.assertTrue(res["ready"])
        live.assert_not_called()
        cl.assert_called_once_with("acc1")
        self.assertTrue(profile_ready(d, "acc1"))

    def test_window_closed_without_disk_still_refuses(self):
        from marketing_divar import chromium_profile as cp
        d = tempfile.mkdtemp()
        save_meta(d, "acc1", {})
        with mock.patch.object(cp, "is_open", return_value=False), \
             mock.patch.object(cp, "_cdp_alive", return_value=False), \
             mock.patch.object(cp, "_cookies_from_live") as live, \
             mock.patch.object(cp, "close_live") as cl:
            res = cp.save_profile(d, "acc1")
        self.assertFalse(res["ok"])
        self.assertEqual(res.get("stage"), "window")
        live.assert_not_called()
        cl.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
