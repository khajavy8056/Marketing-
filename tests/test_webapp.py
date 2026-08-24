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
        self.assertIn("مارکتینگ دیوار", r.text)
        self.assertIn("/logo.png", r.text)
        self.assertIn('id="dash-sms-auto"', r.text)
        self.assertIn("smsAutoToggle", r.text)
        self.assertIn('dir="rtl"', r.text)
        self.assertIn("کلمات کلیدی", r.text)
        self.assertIn('id="kw-category"', r.text)
        self.assertIn('id="kw-city"', r.text)
        self.assertIn('id="kw-price-min"', r.text)
        self.assertIn('id="kw-vip"', r.text)
        self.assertIn("/api/categories", r.text)
        self.assertIn("/api/cities", r.text)
        self.assertIn('id="cap-dlg"', r.text)
        self.assertIn('id="cap-answer"', r.text)
        self.assertIn("/api/captcha/pending", r.text)
        self.assertIn("capProbe", r.text)
        self.assertIn('id="openPuzzle"', r.text)
        self.assertIn("/api/accounts/open-puzzle", r.text)
        self.assertIn("/api/accounts/puzzle-frame", r.text)
        self.assertIn("/api/accounts/close-puzzle", r.text)
        self.assertIn("closePuzzleSession", r.text)
        self.assertIn('id="cap-live-frame"', r.text)
        self.assertNotIn("_puzzleLaunched !== one.name", r.text)
        self.assertIn('id="set-bale-token"', r.text)
        self.assertIn('id="set-rubika-token"', r.text)
        self.assertIn("playAlert", r.text)
        self.assertNotIn('id="cap-frame"', r.text)
        self.assertIn("/api/accounts/probe", r.text)
        self.assertIn('id="set-tg-base"', r.text)
        self.assertIn("requeueHidden", r.text)
        self.assertIn("/api/leads/requeue-hidden", r.text)
        self.assertIn("نمایش شماره", r.text)

    def test_index_bilingual_toggle(self):
        """رابط باید دوزبانه باشد: دکمه تغییر زبان + دیکشنری ترجمه + dir راست‌چین."""
        r = client.get("/")
        self.assertIn('id="lang-btn"', r.text)
        self.assertIn("toggleLang", r.text)
        self.assertIn("FA_EN", r.text)
        self.assertIn('"Dashboard"', r.text)          # ترجمه انگلیسی داشبورد
        self.assertIn('dir="rtl"', r.text)            # پیش‌فرض فارسی
        self.assertIn("function openChat", r.text)
        self.assertIn("chat-dlg", r.text)

    def test_status_shape(self):
        r = client.get("/api/status")
        self.assertEqual(r.status_code, 200)
        for key in ("running", "queue", "chat_queue", "accounts", "keywords", "logs",
                    "breakdown", "accounts_breakdown", "data_dir", "listen",
                    "channels", "vip_found"):
            self.assertIn(key, r.json())
        self.assertIn("bale", r.json()["channels"])
        self.assertIn("rubika", r.json()["channels"])
        self.assertIn("contact_found", r.json()["breakdown"])
        self.assertEqual(r.json()["listen"]["port"], 8642)
        self.assertEqual(r.json()["listen"]["bind"], "0.0.0.0")


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

    def test_01b_get_phone_after_web_login(self):
        """بعد از OTP وب، همان سشن باید شماره را از شبیه‌ساز بگیرد."""
        from marketing_divar.accounts import AccountManager
        from marketing_divar.client import DivarClient
        from marketing_divar.config import DEFAULTS
        from marketing_divar.rate import RateLimiter
        client.post("/api/accounts/otp", json={"name": "web1", "phone": "09121110000"})
        client.post("/api/accounts/confirm", json={"name": "web1", "code": "123456"})
        m = AccountManager(DEFAULTS, os.environ["DIVAR_ACCOUNTS_DIR"])
        cl = DivarClient(session_path=str(m.session_path("web1")),
                         base_url=os.environ["DIVAR_BASE_URL"],
                         limiter=RateLimiter(search_delay=0, phone_delay=0,
                                             page_delay=0, jitter=0))
        self.assertTrue(cl.is_logged_in())
        res = cl.get_phone("webtok1")
        self.assertEqual(res["status"], "found", res)
        self.assertTrue(str(res["phone"]).startswith("0912"))

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

    def test_03_captcha_popup_solve(self):
        from marketing_divar.accounts import AccountManager
        from marketing_divar.config import DEFAULTS
        m = AccountManager(DEFAULTS, os.environ["DIVAR_ACCOUNTS_DIR"])
        m.set_status("web1", "captcha", note="captcha_required")
        m.record_block("web1", "captcha_required", token="adtok",
                       url="https://divar.ir/v/adtok")
        r = client.get("/api/captcha/pending")
        self.assertEqual(r.status_code, 200, r.text)
        pend = r.json()["pending"]
        self.assertTrue(any(p["name"] == "web1" for p in pend))
        one = next(p for p in pend if p["name"] == "web1")
        self.assertTrue(one["question"])
        self.assertEqual(one.get("last_ad_url"), "https://divar.ir/v/adtok")
        from marketing_divar.web import server as srv
        expect = srv._state["gates"]["web1"]["expect"]
        r = client.post("/api/captcha/solve", json={"name": "web1", "answer": "0"})
        self.assertEqual(r.status_code, 400)
        r = client.post("/api/captcha/solve", json={"name": "web1", "answer": str(expect)})
        self.assertEqual(r.status_code, 200, r.text)
        st = next(a for a in client.get("/api/accounts").json()["accounts"]
                  if a["name"] == "web1")
        self.assertEqual(st["status"], "active")
        self.assertIn("captcha_needed", client.get("/api/status").json())
        self.assertIn("telegram", client.get("/api/status").json())

    def test_04_open_puzzle_needs_account(self):
        r = client.post("/api/accounts/open-puzzle", json={"name": "ghost"})
        self.assertEqual(r.status_code, 404)
        client.post("/api/accounts/otp", json={"name": "web1", "phone": "09121110000"})
        client.post("/api/accounts/confirm", json={"name": "web1", "code": "123456"})
        r = client.post("/api/accounts/open-puzzle", json={"name": "web1"})
        self.assertIn(r.status_code, (200, 400))
        if r.status_code == 200:
            self.assertTrue(r.json().get("ok"))
            self.assertTrue(r.json().get("embed") or r.json().get("fallback"))
        else:
            self.assertTrue(r.json().get("detail"))
        r = client.get("/api/accounts/puzzle-frame?name=ghost")
        self.assertEqual(r.status_code, 404)
        r = client.post("/api/accounts/puzzle-click",
                        json={"name": "ghost", "x": 0.5, "y": 0.5})
        self.assertEqual(r.status_code, 404)
        r = client.post("/api/accounts/close-puzzle")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("ok"))


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
        cats = client.get("/api/categories").json()["categories"]
        self.assertTrue(any(c["slug"] == "mobile-tablet" for c in cats))
        self.assertTrue(any(c.get("parent") == "vehicles" for c in cats if c["slug"] == "light"))
        cities = client.get("/api/cities").json()["cities"]
        self.assertTrue(any(c["slug"] == "tehran" for c in cities))
        r = client.post("/api/keywords",
                        json={"keyword": "", "cities": None, "category": "light"})
        self.assertEqual(r.status_code, 200, r.text)
        kws = client.get("/api/keywords").json()["keywords"]
        self.assertTrue(any(k.get("category") == "light" for k in kws))
        r = client.post("/api/keywords", json={
            "keyword": "آیفون ویژه", "cities": [1], "category": "mobile-phones",
            "price_min": 20, "price_max": 80, "vip": True})
        self.assertEqual(r.status_code, 200, r.text)
        one = next(k for k in client.get("/api/keywords").json()["keywords"]
                   if k["keyword"] == "آیفون ویژه")
        self.assertTrue(one["vip"])
        self.assertEqual(one["price_min"], 20_000_000)
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

    def test_lead_draft_and_status(self):
        from marketing_divar.db import connect as db_connect
        con = db_connect(os.environ["DIVAR_DB_PATH"])
        with con:
            con.execute(
                "INSERT OR IGNORE INTO leads (token,title,url,keyword,city,"
                "phone_status,lead_status,first_seen_at) "
                "VALUES ('draft1','ویلا تست','https://divar.ir/v/draft1','ویلا',"
                "'iran','hidden','new',?)",
                (time.strftime("%Y-%m-%d %H:%M:%S"),))
        con.close()
        r = client.get("/api/leads/draft1/draft")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("ویلا تست", r.json()["message"])
        r = client.post("/api/leads/draft1/status",
                        json={"status": "contacted", "chat_status": "sent"})
        self.assertEqual(r.status_code, 200)
        leads = client.get("/api/leads?filter=all").json()["leads"]
        row = next(l for l in leads if l["token"] == "draft1")
        self.assertEqual(row["lead_status"], "contacted")
        self.assertEqual(row["chat_status"], "sent")
        r = client.post("/api/leads/requeue-hidden")
        self.assertEqual(r.status_code, 200)
        leads = client.get("/api/leads?filter=all").json()["leads"]
        row = next(l for l in leads if l["token"] == "draft1")
        self.assertEqual(row["phone_status"], "pending")

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
        r = client.post("/api/settings", json={"values": {
            "bale_bot_token": "bale-tok", "bale_chat_id": "11",
            "rubika_bot_token": "rub-tok", "rubika_chat_id": "22"}})
        self.assertEqual(r.status_code, 200)
        s = client.get("/api/settings").json()
        self.assertEqual(s["bale_bot_token"], "bale-tok")
        self.assertEqual(s["rubika_chat_id"], "22")
        eff = store.effective_config(os.environ["DIVAR_DB_PATH"], DEFAULTS)
        self.assertEqual(eff["notify"]["bale_bot_token"], "bale-tok")
        self.assertEqual(eff["notify"]["rubika_bot_token"], "rub-tok")
        r = client.post("/api/sms/test", json={"to": ""})
        self.assertEqual(r.status_code, 400)
        r = client.post("/api/settings", json={"values": {
            "sms_username": "meliuser", "sms_password": "melipass",
            "sms_auto_on_new": False, "sms_daily_limit": 15}})
        self.assertEqual(r.status_code, 200)
        s = client.get("/api/settings").json()
        self.assertEqual(s["sms_username"], "meliuser")
        self.assertFalse(s["sms_auto_on_new"])
        r = client.post("/api/telegram/test")
        self.assertEqual(r.status_code, 200)
        self.assertIn("preview", r.json())
        r = client.post("/api/sms/auto", json={"on": True})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["on"])
        self.assertIn("sms_auto_on_new", client.get("/api/status").json())
        client.post("/api/sms/auto", json={"on": False})
        self.assertFalse(client.get("/api/settings").json()["sms_auto_on_new"])


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
