# -*- coding: utf-8 -*-
"""تست یکپارچهٔ app سرور: احراز هویت + endpoint های پروفایل (نشست ریموت).

در حالت DIVAR_SERVER_NO_VNC=1 اجرا می‌شود (بدون Xvfb واقعی).
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "server"))

os.environ["DIVAR_SERVER_NO_VNC"] = "1"
os.environ["DIVAR_DATA_DIR"] = tempfile.mkdtemp()

from starlette.testclient import TestClient  # noqa: E402
from divar_server.app import build_app  # noqa: E402


class TestApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = build_app()
        cls.c = TestClient(cls.app)

    def _login(self):
        self.c.post("/api/auth/login",
                    json={"username": "admin", "password": "admin"})

    def test_unauth_redirect_to_login(self):
        # کلاینت تازه (بدون کوکی نشست) تا واقعاً «بدون احراز» باشد
        fresh = TestClient(self.app)
        r = fresh.get("/", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers.get("location"), "/login")

    def test_login_and_panel(self):
        self._login()
        r = self.c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("remote-card", r.text)  # تزریق UI سرور

    def test_api_blocked_without_auth(self):
        r = self.c.post("/api/remote/foo/open", json={})
        self.assertEqual(r.status_code, 401)

    def test_profile_create_open_save_delete(self):
        self._login()
        # ساخت پروفایل → نشست ریموت (fake)
        r = self.c.post("/api/accounts/profile/create",
                        json={"name": "ali", "phone": "09120000000"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json().get("ok"))
        # باز کردن مجدد → already_open
        r = self.c.post("/api/accounts/profile/open", json={"name": "ali"})
        self.assertEqual(r.status_code, 200)
        # ذخیره (لاگین دیده نمی‌شود چون پروفایل خالی است) → ready=False
        r = self.c.post("/api/accounts/profile/save", json={"name": "ali"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("ready", r.json())
        # حذف
        r = self.c.post("/api/accounts/profile/delete", json={"name": "ali"})
        self.assertEqual(r.status_code, 200)

    def test_remote_endpoints_require_session(self):
        self._login()
        r = self.c.post("/api/remote/ali/open", json={})
        self.assertEqual(r.status_code, 200)
        r = self.c.get("/api/remote/ali/status")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("open"))
        r = self.c.post("/api/remote/ali/close", json={})
        self.assertEqual(r.status_code, 200)

    def test_logout(self):
        self._login()
        r = self.c.post("/api/auth/logout", json={})
        self.assertEqual(r.status_code, 200)
        # بعد از خروج → ریدایرکت
        r = self.c.get("/", follow_redirects=False)
        self.assertEqual(r.status_code, 302)

    def test_ws_relay_rejects_when_session_closed(self):
        """بدون نشست باز، پل WS باید رد شود (رجعت باگ «open» در سطح اشتباه)."""
        from divar_server import remote_session
        from starlette.websockets import WebSocketDisconnect
        remote_session.close_all()
        with self.assertRaises(WebSocketDisconnect):
            with self.c.websocket_connect("/api/remote/none/ws"):
                pass

    def test_status_open_is_top_level(self):
        """«open» در سطح بالای status است (نه داخل session) — رگرسیون باگ رله."""
        from divar_server import remote_session
        remote_session.open_remote(self._acc_dir(), "t")
        st = remote_session.status("t")
        self.assertTrue(st.get("open"))
        self.assertIn("ws_port", st.get("session", {}))
        remote_session.close_remote("t")

    def _acc_dir(self):
        import os
        return os.environ.get("DIVAR_ACCOUNTS_DIR", "data/accounts")


if __name__ == "__main__":
    unittest.main()
