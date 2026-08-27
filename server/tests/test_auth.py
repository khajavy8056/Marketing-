# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest
from pathlib import Path

# مسیرها: server/ و ریشهٔ مخزن برای import بسته‌ها
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "server"))

_TMP = tempfile.mkdtemp()
os.environ["DIVAR_DATA_DIR"] = _TMP

from divar_server import auth as auth_mod  # noqa: E402
from divar_server.auth import AuthManager, _verify_password, _hash_password  # noqa: E402


class TestAuth(unittest.TestCase):
    def setUp(self):
        self.mgr = AuthManager()
        self.mgr._creds_path = Path(_TMP) / "server-auth-test.json"
        # ساخت حالت پیش‌فرض
        self.mgr._write({"users": {"admin": {
            "password_hash": _hash_password("admin"),
            "must_change_password": True,
        }}})

    def test_default_credentials_login(self):
        r = self.mgr.authenticate("admin", "admin")
        self.assertTrue(r["ok"])
        self.assertTrue(r["must_change_password"])

    def test_wrong_password_rejected(self):
        r = self.mgr.authenticate("admin", "wrong")
        self.assertFalse(r["ok"])

    def test_session_valid_and_logout(self):
        r = self.mgr.authenticate("admin", "admin")
        self.assertTrue(self.mgr.get_session(r["token"]))
        self.mgr.logout(r["token"])
        self.assertIsNone(self.mgr.get_session(r["token"]))

    def test_change_password(self):
        r = self.mgr.authenticate("admin", "admin")
        ch = self.mgr.change_password(r["token"], "admin", "newsecret")
        self.assertTrue(ch["ok"])
        # رمز قدیمی دیگر کار نمی‌کند
        self.assertFalse(self.mgr.authenticate("admin", "admin")["ok"])
        # رمز جدید کار می‌کند و دیگر اجبار تغییر ندارد
        r2 = self.mgr.authenticate("admin", "newsecret")
        self.assertTrue(r2["ok"])
        self.assertFalse(r2["must_change_password"])

    def test_change_password_too_short(self):
        r = self.mgr.authenticate("admin", "admin")
        ch = self.mgr.change_password(r["token"], "admin", "123")
        self.assertFalse(ch["ok"])

    def test_hash_roundtrip(self):
        h = _hash_password("abc123")
        self.assertTrue(_verify_password("abc123", h))
        self.assertFalse(_verify_password("abc124", h))


if __name__ == "__main__":
    unittest.main()
