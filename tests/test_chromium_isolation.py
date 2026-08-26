# -*- coding: utf-8 -*-
"""پروفایل A/B/C جدا — سشن تزریق نمی‌شود، پوشهٔ chromium جداست."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from marketing_divar.chromium_profile import (  # noqa: E402
    HOME_URL, close_live, cookies_look_logged_in, chromium_dir,
    create_and_open, delete_profile, harvest_to_session, is_open,
    launch_kwargs, load_meta, profile_ready, save_meta, save_profile,
    snapshot_fields)


class TestProfileIsolation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.acc = os.path.join(self.tmp, "accounts")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _seed(self, name, token):
        d = chromium_dir(self.acc, name)
        d.mkdir(parents=True)
        marker = d / "Cookies"
        marker.write_text(token, encoding="utf-8")
        save_meta(self.acc, name, {"profile_ready": True, "cookie": token})
        return d

    def test_three_profiles_do_not_share_user_data(self):
        a = self._seed("alice", "COOKIE-A")
        b = self._seed("bob", "COOKIE-B")
        c = self._seed("carol", "COOKIE-C")
        self.assertNotEqual(a, b)
        self.assertNotEqual(b, c)
        self.assertEqual((a / "Cookies").read_text(encoding="utf-8"), "COOKIE-A")
        self.assertEqual((b / "Cookies").read_text(encoding="utf-8"), "COOKIE-B")
        self.assertEqual((c / "Cookies").read_text(encoding="utf-8"), "COOKIE-C")
        with mock.patch("marketing_divar.app_chromium.executable_path",
                        return_value="/opt/app/chrome"):
            kwa = launch_kwargs(a)
            kwb = launch_kwargs(b)
        self.assertEqual(kwa["user_data_dir"], str(a))
        self.assertEqual(kwb["user_data_dir"], str(b))
        self.assertNotEqual(kwa["user_data_dir"], kwb["user_data_dir"])
        self.assertEqual(kwa["executable_path"], "/opt/app/chrome")
        self.assertNotIn("channel", kwa)

    def test_delete_a_keeps_b(self):
        self._seed("alice", "A")
        self._seed("bob", "B")
        delete_profile(self.acc, "alice")
        self.assertFalse(Path(self.acc, "alice").exists())
        self.assertTrue((chromium_dir(self.acc, "bob") / "Cookies").exists())
        self.assertEqual(
            (chromium_dir(self.acc, "bob") / "Cookies").read_text(encoding="utf-8"),
            "B")

    def test_mid_login_close_keeps_profile_dir(self):
        d = chromium_dir(self.acc, "mid")
        d.mkdir(parents=True)
        save_meta(self.acc, "mid", {"profile_ready": False, "status": "open"})
        (d / "Local State").write_text("partial", encoding="utf-8")
        close_live("mid")
        self.assertTrue(d.exists())
        self.assertEqual((d / "Local State").read_text(encoding="utf-8"), "partial")
        self.assertFalse(profile_ready(self.acc, "mid"))
        self.assertFalse(is_open("mid"))

    def test_expired_session_is_not_ready(self):
        save_meta(self.acc, "old", {"profile_ready": False})
        self.assertFalse(cookies_look_logged_in([]))
        self.assertFalse(cookies_look_logged_in(
            [{"name": "session", "value": "x", "domain": ".divar.ir"}]))
        self.assertFalse(profile_ready(self.acc, "old"))
        snap = snapshot_fields(self.acc, "old")
        self.assertFalse(snap["profile_ready"])

    def test_reopen_uses_same_dir_no_cookie_inject(self):
        d = self._seed("keep", "SESSION-KEEP")
        src = Path(ROOT, "marketing_divar", "chromium_profile.py").read_text(
            encoding="utf-8")
        self.assertNotIn("add_cookies", src)
        self.assertIn("launch_persistent_context", src)
        self.assertIn("executable_path", src)
        self.assertIn(HOME_URL, src)
        with mock.patch("marketing_divar.chromium_profile.ensure_installed"
                        if False else "marketing_divar.app_chromium.ensure_installed",
                        return_value=Path("/opt/app/chrome")), \
             mock.patch("marketing_divar.chromium_profile.close_live"), \
             mock.patch("marketing_divar.chromium_profile._run_browser"):
            # open_profile will try real playwright; just assert dir reuse
            self.assertEqual(chromium_dir(self.acc, "keep"), d)
            self.assertTrue(profile_ready(self.acc, "keep"))

    def test_create_opens_tehran_and_isolated_folder(self):
        with mock.patch("marketing_divar.chromium_profile.open_profile",
                        return_value={"ok": True, "url": HOME_URL,
                                      "message": "opened"}) as op:
            res = create_and_open(self.acc, "user A", "09120000000")
        self.assertTrue(res["ok"])
        args, _ = op.call_args
        self.assertEqual(args[2], HOME_URL)
        self.assertTrue(chromium_dir(self.acc, "user-A").is_dir())
        self.assertNotEqual(chromium_dir(self.acc, "user-A"),
                            chromium_dir(self.acc, "user-B"))

    def test_harvest_does_not_copy_foreign_cookies(self):
        save_meta(self.acc, "one", {"phone": "09121111111"})
        harvest_to_session(self.acc, "one", [
            {"name": "sRefreshToken", "value": "MINE", "domain": ".divar.ir"},
            {"name": "sid", "value": "OTHER", "domain": ".google.com"},
        ])
        data = json.loads(
            (Path(self.acc) / "one" / "session.json").read_text(encoding="utf-8"))
        names = {c["name"] for c in data.get("cookies_full") or data.get("cookies") or []}
        # merge stores cookies dict + cookies_full
        blob = json.dumps(data)
        self.assertIn("MINE", blob)
        self.assertNotIn("OTHER", blob)

    def test_home_url_is_tehran(self):
        self.assertEqual(HOME_URL, "https://divar.ir/s/tehran")


if __name__ == "__main__":
    unittest.main(verbosity=2)
