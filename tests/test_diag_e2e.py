# -*- coding: utf-8 -*-
"""تست سرتاسری «بررسی اتصال کامل» (/api/diag) روی شبیه‌ساز دیوار."""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

TMP = tempfile.mkdtemp()
os.environ["DIVAR_DB_PATH"] = os.path.join(TMP, "diag.db")
os.environ["DIVAR_ACCOUNTS_DIR"] = os.path.join(TMP, "acc")

from mock_divar import MockDivar, start_mock  # noqa: E402

_srv = start_mock()
os.environ["DIVAR_BASE_URL"] = f"http://127.0.0.1:{_srv.server_address[1]}"

MockDivar.add_posts([
    {"token": f"dg{i:03d}", "title": f"آپارتمان {i}", "has_chat": False}
    for i in range(6)])

from fastapi.testclient import TestClient  # noqa: E402
from marketing_divar.web.server import app  # noqa: E402

c = TestClient(app)


class TestDiagEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert c.post("/api/accounts/otp",
                      json={"name": "dacc", "phone": "09120000000"}).json()["ok"]
        assert c.post("/api/accounts/confirm",
                      json={"name": "dacc", "phone": "09120000000",
                            "code": "111111"}).json()["ok"]
        c.post("/api/keywords", json={"keyword": "آپارتمان"})

    def test_diag_runs_all_steps(self):
        r = c.post("/api/diag")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        keys = [s["key"] for s in d["steps"]]
        for must in ("dns", "connect", "search", "detail", "phone_anon",
                     "phone_auth", "chat", "proxy"):
            self.assertIn(must, keys)
        by = {s["key"]: s for s in d["steps"]}
        self.assertTrue(by["dns"]["ok"])
        self.assertTrue(by["search"]["ok"])
        self.assertIn("آگهی", by["search"]["detail"])
        self.assertTrue(by["detail"]["ok"], by["detail"])
        self.assertIn("لازم است", by["phone_anon"]["detail"],
                      "شبیه‌ساز بدون لاگین ۴۰۱ می‌دهد — آزمایش علمی")
        self.assertTrue(by["phone_auth"]["ok"], by["phone_auth"])
        self.assertIn("شماره", by["phone_auth"]["detail"])
        self.assertFalse(by["chat"]["ok"], "شبیه‌ساز اندپوینت چت ندارد → ✗ صادقانه")
        self.assertTrue(by["proxy"]["ok"], "در تست پروکسی نباید فعال باشد")
        self.assertIn("proxy", d)
        # رخدادها هم ثبت شده باشند
        logs = " ".join(l["msg"] for l in c.get("/api/status").json()["logs"])
        self.assertIn("بررسی اتصال تمام شد", logs)


if __name__ == "__main__":
    unittest.main()
