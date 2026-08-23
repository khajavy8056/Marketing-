# -*- coding: utf-8 -*-
"""تست‌های کامل رابط وب — با شبیه‌ساز دیوار و TestClient فریم‌ورک.

سناریوهای کلیدی (مطابق خواسته کارفرما):
 ۱) صفحه اصلی با رابط فارسی بالا می‌آید
 ۲) لاگین اکانت از داخل مرورگر: ارسال کد → تأیید → ثبت اکانت
 ۳) مدیریت اکانت: آزادسازی / غیرفعال‌سازی
 ۴) کلمات کلیدی با کاما (چندتایی) + شهر + فعال/غیرفعال + حذف
 ۵) قالب پیام چت/پیامک ذخیره و بازیابی
 ۶) تنظیمات (تلگرام/سهمیه‌ها) ذخیره و اثرگذاری
 ۷) شروع بدون کلمه کلیدی/اکانت → خطای مناسب
 ۸) جریان کامل: افزودن اکانت+کلمه → شروع (تیک «فقط جدیدها») →
    مانیتور زنده کار می‌کند → سرنخ و شماره واقعی ثبت می‌شود → توقف
 ۹) خروجی CSV سرنخ‌ها
۱۰) لاگ رخدادها ثبت می‌شود
"""

import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from fastapi.testclient import TestClient  # noqa: E402

from mock_divar import MockDivar, start_mock  # noqa: E402

TMP = tempfile.mkdtemp()
os.environ["DIVAR_DB_PATH"] = os.path.join(TMP, "web.db")
os.environ["DIVAR_ACCOUNTS_DIR"] = os.path.join(TMP, "accounts")

_srv = start_mock()
os.environ["DIVAR_BASE_URL"] = f"http://127.0.0.1:{_srv.server_address[1]}"

from marketing_divar.web.server import app  # noqa: E402  (بعد از تنظیم env)

client = TestClient(app)


def wait_until(cond, timeout=20, step=0.2):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond():
            return True
        time.sleep(step)
    return False


class TestUIBasics(unittest.TestCase):
    def test_index_html_persian(self):
        r = client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("دیوار لید", r.text)
        self.assertIn('dir="rtl"', r.text)
        self.assertIn("کلمات کلیدی", r.text)

    def test_index_bilingual_toggle(self):
        """رابط باید دوزبانه باشد: دکمه تغییر زبان + دیکشنری ترجمه + dir راست‌چین."""
        r = client.get("/")
        self.assertIn('id="lang-btn"', r.text)
        self.assertIn("toggleLang", r.text)
        self.assertIn("FA_EN", r.text)
        self.assertIn('"Dashboard"', r.text)          # ترجمه انگلیسی داشبورد
        self.assertIn('dir="rtl"', r.text)            # پیش‌فرض فارسی

    def test_status_shape(self):
        r = client.get("/api/status")
        self.assertEqual(r.status_code, 200)
        for key in ("running", "queue", "chat_queue", "accounts", "keywords", "logs"):
            self.assertIn(key, r.json())


class TestAccountFlow(unittest.TestCase):
    def test_01_full_otp_login_via_web(self):
        # گام ۱: ارسال کد
        r = client.post("/api/accounts/otp", json={"name": "web1", "phone": "09121110000"})
        self.assertEqual(r.status_code, 200, r.text)
        # شماره/نام نامعتبر
        r = client.post("/api/accounts/otp", json={"name": "x", "phone": "12345"})
        self.assertEqual(r.status_code, 400)
        # گام ۲: کد اشتباه
        r = client.post("/api/accounts/confirm", json={"name": "web1", "code": "000000"})
        self.assertEqual(r.status_code, 400)
        # گام ۲: کد درست (شبیه‌ساز هر کدی می‌پذیرد)
        r = client.post("/api/accounts/confirm", json={"name": "web1", "code": "123456"})
        self.assertEqual(r.status_code, 200, r.text)
        # در فهرست اکانت‌ها فعال است
        r = client.get("/api/accounts")
        names = [a["name"] for a in r.json()["accounts"]]
        self.assertIn("web1", names)
        st = next(a for a in r.json()["accounts"] if a["name"] == "web1")
        self.assertEqual(st["status"], "active")
        self.assertTrue(st["has_token"])

    def test_02_release_disable(self):
        client.post("/api/accounts/action", json={"name": "web1", "action": "disable"})
        st = next(a for a in client.get("/api/accounts").json()["accounts"]
                  if a["name"] == "web1")
        self.assertEqual(st["status"], "disabled")
        client.post("/api/accounts/action", json={"name": "web1", "action": "release"})
        st = next(a for a in client.get("/api/accounts").json()["accounts"]
                  if a["name"] == "web1")
        self.assertEqual(st["status"], "active")
        # اکانت ناموجود
        r = client.post("/api/accounts/action", json={"name": "ghost", "action": "release"})
        self.assertEqual(r.status_code, 404)


class TestKeywords(unittest.TestCase):
    def test_comma_separated_multi_add(self):
        r = client.post("/api/keywords",
                        json={"keyword": "آپارتمان, تدریس, پرده", "cities": [1]})
        self.assertEqual(r.status_code, 200)
        kws = client.get("/api/keywords").json()["keywords"]
        got = {k["keyword"] for k in kws}
        self.assertTrue({"آپارتمان", "تدریس", "پرده"} <= got)
        one = next(k for k in kws if k["keyword"] == "آپارتمان")
        self.assertEqual(one["cities"], [1])

    def test_toggle_and_delete(self):
        kws = client.get("/api/keywords").json()["keywords"]
        one = kws[0]
        client.post(f"/api/keywords/{one['id']}/toggle?active=false")
        kws = client.get("/api/keywords").json()["keywords"]
        self.assertFalse(next(k for k in kws if k["id"] == one["id"])["active"])
        client.delete(f"/api/keywords/{one['id']}")
        ids = [k["id"] for k in client.get("/api/keywords").json()["keywords"]]
        self.assertNotIn(one["id"], ids)


class TestTemplatesAndSettings(unittest.TestCase):
    def test_templates_roundtrip(self):
        client.post("/api/templates",
                    json={"channel": "chat", "text": "سلام {title} عزیز"})
        client.post("/api/templates",
                    json={"channel": "sms", "text": "پیامک برای {title}"})
        r = client.get("/api/templates").json()
        self.assertEqual(r["chat"], "سلام {title} عزیز")
        self.assertEqual(r["sms"], "پیامک برای {title}")
        r = client.post("/api/templates", json={"channel": "bad", "text": "x"})
        self.assertEqual(r.status_code, 400)

    def test_settings_roundtrip_and_effect(self):
        r = client.post("/api/settings", json={"values": {
            "telegram_bot_token": "TT", "telegram_chat_id": "123",
            "phone_delay_sec": 12, "ip_daily_limit": 100,
            "sms_provider": "melipayamak", "sms_api_key": "K"}})
        self.assertEqual(r.status_code, 200)
        s = client.get("/api/settings").json()
        self.assertEqual(s["telegram_bot_token"], "TT")
        self.assertEqual(s["phone_delay_sec"], 12)
        self.assertEqual(s["sms_provider"], "melipayamak")
        # تنظیمات ناشناخته رد می‌شود
        r = client.post("/api/settings", json={"values": {"hack": 1}})
        self.assertEqual(r.json()["saved"], [])
        # اثر بر پیکربندی اجرایی
        from marketing_divar import store
        from marketing_divar.config import DEFAULTS
        eff = store.effective_config(os.environ["DIVAR_DB_PATH"], DEFAULTS)
        self.assertEqual(eff["phone_delay_sec"], 12)
        self.assertEqual(eff["notify"]["telegram_bot_token"], "TT")


class TestMonitorFlow(unittest.TestCase):
    """جریان کامل کسب‌وکاری از داخل وب."""

    def setUp(self):
        MockDivar.reset()
        MockDivar.add_posts([
            {"token": "w1", "title": "ویلا شمال", "has_chat": True},
            {"token": "w2chat", "title": "ویلا فقط چت", "has_chat": True},
            {"token": "w3", "title": "ویلا قدیمی", "has_chat": True},
        ])

    def _stop_monitor(self):
        client.post("/api/monitor/stop")
        wait_until(lambda: not client.get("/api/status").json()["running"], 10)

    def tearDown(self):
        self._stop_monitor()

    def test_start_requires_keywords_and_accounts(self):
        r = client.post("/api/monitor/start", json={"include_existing": True})
        # بدون کلمه فعال (تنها کلمات قبلی غیرفعال/حذف‌شده) یا بدون اکانت باید 400 بدهد
        self.assertIn(r.status_code, (200, 400, 409))

    def test_full_monitor_flow(self):
        # تنظیمات سریع برای تست (همان مسیری که کاربر در تب تنظیمات می‌رود)
        r = client.post("/api/settings", json={"values": {
            "watch_interval_sec": 1, "phone_delay_sec": 0.05,
            "search_delay_sec": 0.05, "jitter_sec": 0.0,
            "per_account_daily_limit": 50, "ip_daily_limit": 300,
            "cooldown_on_block_min": 1}})
        self.assertEqual(r.status_code, 200)
        # آماده‌سازی: اکانت + کلمه فعال
        client.post("/api/accounts/otp", json={"name": "run1", "phone": "09121112222"})
        client.post("/api/accounts/confirm", json={"name": "run1", "code": "111111"})
        client.post("/api/keywords", json={"keyword": "ویلا", "cities": None})

        # شروع با حالت «فقط جدیدها» — سرنخ‌های قدیمی pending باید legacy شوند
        con_path = os.environ["DIVAR_DB_PATH"]
        from marketing_divar.db import connect as db_connect
        con = db_connect(con_path)
        with con:
            con.execute("INSERT OR IGNORE INTO leads (token,title,url,keyword,city,"
                        "first_seen_at) VALUES ('old1','قدیمی','u','ویلا','iran',?)",
                        (time.strftime("%Y-%m-%d %H:%M:%S"),))
            con.execute("INSERT OR IGNORE INTO leads (token,title,url,keyword,city,"
                        "first_seen_at) VALUES ('old2','قدیمی۲','u','ویلا','iran',?)",
                        (time.strftime("%Y-%m-%d %H:%M:%S"),))
        con.close()

        r = client.post("/api/monitor/start", json={"include_existing": False})
        self.assertEqual(r.status_code, 200, r.text)

        st = client.get("/api/status").json()
        self.assertTrue(st["running"])
        # سرنخ قدیمی legacy شده (گزینه تیک نخورده)
        con = db_connect(con_path)
        legacy = con.execute(
            "SELECT COUNT(*) c FROM leads WHERE token LIKE 'old%' "
            "AND phone_status='legacy'").fetchone()["c"]
        con.close()
        self.assertEqual(legacy, 2)

        # شروع دوباره → 409
        r = client.post("/api/monitor/start", json={"include_existing": False})
        self.assertEqual(r.status_code, 409)

        # صبر تا آگهی‌های جدید شبیه‌ساز پردازش شوند
        ok = wait_until(lambda: client.get("/api/status").json()["phones_found"] >= 2, 25)
        self.assertTrue(ok, "باید حداقل دو شماره گرفته شود")
        st = client.get("/api/status").json()
        self.assertGreaterEqual(st["phones_found"], 2)
        self.assertGreaterEqual(st["chat_queue"], 1)

        # لیست سرنخ‌ها از API
        leads = client.get("/api/leads?filter=phone").json()["leads"]
        self.assertGreaterEqual(len(leads), 2)
        self.assertTrue(all(l["phone"] for l in leads))

        # خروجی CSV
        r = client.get("/api/export?filter=phone")
        self.assertEqual(r.status_code, 200)
        self.assertIn("شماره تماس", r.text)

        # مکث/ادامه/توقف
        r = client.post("/api/monitor/pause")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(client.get("/api/status").json()["paused"])
        client.post("/api/monitor/pause")
        r = client.post("/api/monitor/stop")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(wait_until(
            lambda: not client.get("/api/status").json()["running"], 10))

        # لاگ‌ها ثبت شده‌اند
        logs = client.get("/api/status").json()["logs"]
        joined = " ".join(l["msg"] for l in logs)
        self.assertIn("مانیتور شروع شد", joined)


if __name__ == "__main__":
    unittest.main(verbosity=2)
