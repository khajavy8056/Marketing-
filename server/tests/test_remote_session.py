# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "server"))

# حالت تست: بدون اجرای Xvfb/x11vnc/websockify واقعی
os.environ["DIVAR_SERVER_NO_VNC"] = "1"
os.environ["DIVAR_DATA_DIR"] = tempfile.mkdtemp()

from divar_server import remote_session as rs  # noqa: E402


class TestRemoteSession(unittest.TestCase):
    def setUp(self):
        self.acc_dir = tempfile.mkdtemp()
        rs.close_all()

    def tearDown(self):
        rs.close_all()

    def test_open_and_status_and_close(self):
        r = rs.open_remote(self.acc_dir, "ali")
        self.assertTrue(r["ok"])
        self.assertEqual(r["account"], "ali")
        self.assertIn("ws_port", r)
        st = rs.status("ali")
        self.assertTrue(st["open"])
        c = rs.close_remote("ali")
        self.assertTrue(c["ok"])
        self.assertFalse(rs.status("ali")["open"])

    def test_already_open_returns_existing(self):
        rs.open_remote(self.acc_dir, "ali")
        r2 = rs.open_remote(self.acc_dir, "ali")
        self.assertTrue(r2["ok"])
        self.assertTrue(r2.get("already_open"))

    def test_close_nonexistent(self):
        r = rs.close_remote("nonexistent")
        self.assertFalse(r["ok"])

    def test_display_pool_isolation(self):
        a = rs.open_remote(self.acc_dir, "a")
        b = rs.open_remote(self.acc_dir, "b")
        self.assertNotEqual(a["display"], b["display"])

    def test_reap_idle(self):
        rs.open_remote(self.acc_dir, "ali")
        # شبیه‌سازی بی‌کار شدن
        with rs._LOCK:
            rs._LIVE["ali"]["last_activity"] = 0.0
        self.assertEqual(rs.reap_idle(), 1)
        self.assertFalse(rs.status("ali")["open"])

    def test_verify_login_empty_profile(self):
        r = rs.verify_login(self.acc_dir, "ali")
        self.assertTrue(r["ok"])
        self.assertFalse(r["logged_in"])

    def test_touch_updates_activity(self):
        rs.open_remote(self.acc_dir, "ali")
        with rs._LOCK:
            rs._LIVE["ali"]["last_activity"] = 0.0
        rs.touch("ali")
        with rs._LOCK:
            self.assertGreater(rs._LIVE["ali"]["last_activity"], 1.0)


if __name__ == "__main__":
    unittest.main()
