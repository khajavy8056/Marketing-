# -*- coding: utf-8 -*-
"""تست‌های ریشه‌ای باگ «همه‌چیز صفر و هیچ اتفاقی نمی‌افتد».

سه ریشهٔ پیدا‌شده و رفع‌شده:
 ۱) پروکسی/VPN سیستم ویندوز توسط requests خودکار اعمال می‌شود و اگر
    قطع/خارج از ایران باشد همهٔ درخواست‌ها به دیوار می‌میرند →
    فیکس: _fetch خودترمیم (تلاش مجدد بدون پروکسی).
 ۲) خطاهای مانیتور فقط در کنسول چاپ می‌شدند و در رخدادنمای وب دیده
    نمی‌شدند → فیکس: on_event.
 ۳) رد شدن دیوار (401/403/451) باید پیام راهنمای «IP ایران» بدهد.
"""

import os
import sys
import tempfile
import unittest

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from marketing_divar.client import DivarClient, DivarBlockedError  # noqa: E402


class _FakeSession:
    """جلسهٔ جعلی: بار اول ProxyError می‌دهد، بعدی‌ها موفق — شبیه VPN قطع‌شده."""

    def __init__(self):
        self.calls = []
        self.trust_env = True
        self.proxies = {}
        self.headers = {}
        self.cookies = {}

    def _hit(self, method, url, **kw):
        self.calls.append((method, url, kw.get("proxies", "default")))
        if len(self.calls) == 1:
            raise requests.exceptions.ProxyError("fake vpn is down")
        return _FakeResp(200, {"widget_list": [], "posts": []})

    def get(self, url, **kw):
        return self._hit("GET", url, **kw)

    def post(self, url, **kw):
        return self._hit("POST", url, **kw)


class _FakeResp:
    def __init__(self, code, payload):
        self.status_code = code
        self._p = payload
        self.text = str(payload)

    def json(self):
        return self._p


class TestProxySelfHeal(unittest.TestCase):
    """۱) خطای پروکسی → تلاش مجدد مستقیم → موفق و ماندگار."""

    def test_proxy_error_falls_back_to_direct(self):
        c = DivarClient.__new__(DivarClient)  # بدون _load_session
        c.http = _FakeSession()
        c.base = "http://x"
        c._direct_forced = False
        c.limiter = __import__("marketing_divar.rate", fromlist=["RateLimiter"]).RateLimiter(
            search_delay=0, phone_delay=0, page_delay=0, jitter=0)
        r = c._fetch("GET", "http://x/ok")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(c.http.calls), 2, "باید یک‌بار retry بدون پروکسی زده شود")
        self.assertFalse(c.http.trust_env, "باید trust_env خاموش بماند")

    def test_second_proxy_error_raises(self):
        c = DivarClient.__new__(DivarClient)
        c.http = _FakeSession()
        c.base = "http://x"
        c._direct_forced = True  # قبلاً مستقیم شده؛ دیگر fallback نیست
        c.limiter = __import__("marketing_divar.rate", fromlist=["RateLimiter"]).RateLimiter(
            search_delay=0, phone_delay=0, page_delay=0, jitter=0)
        with self.assertRaises(requests.exceptions.ProxyError):
            c._fetch("GET", "http://x/ok")


class TestBlockedHint(unittest.TestCase):
    """۳) 403 → DivarBlockedError با راهنمای VPN/IP ایران."""

    def test_403_gives_iran_ip_hint(self):
        c = DivarClient.__new__(DivarClient)
        c.http = _FakeSession()
        c.http._always = _FakeResp(403, {})
        c.base = "http://x"
        c._direct_forced = False
        c.limiter = __import__("marketing_divar.rate", fromlist=["RateLimiter"]).RateLimiter(
            search_delay=0, phone_delay=0, page_delay=0, jitter=0)
        # همه پاسخ‌ها 403 برگردند
        c.http.get = lambda u, **kw: _FakeResp(403, {})
        with self.assertRaises(DivarBlockedError) as cm:
            c.search("آپارتمان")
        self.assertIn("IP ایران", str(cm.exception))


class TestMonitorEvents(unittest.TestCase):
    """۲) خطای جستجو باید به on_event برسد (رخدادنمای وب)."""

    def test_search_error_reaches_events(self):
        from marketing_divar.monitor import Monitor
        events = []

        class _Boom:
            def search(self, *a, **k):
                raise requests.exceptions.ConnectionError("connection refused")

        m = Monitor(cfg={"watch_interval_sec": 1}, keywords=[{"keyword": "x"}],
                    db_path=os.path.join(tempfile.mkdtemp(), "m.db"),
                    accounts_dir=os.path.join(tempfile.mkdtemp(), "acc"),
                    interactive=False)
        m._anon = _Boom()  # تزریق کلاینت خراب
        m.on_event = lambda lvl, msg: events.append((lvl, msg))
        m.watch_once()
        self.assertTrue(any(lvl == "error" and "x" in msg for lvl, msg in events),
                        f"رخداد خطا ثبت نشد: {events}")
        self.assertTrue(any("اینترنت" in msg or "بررسی" in msg for _, msg in events),
                        "راهنمای عیب‌یابی در پیام نیست")


if __name__ == "__main__":
    unittest.main()
