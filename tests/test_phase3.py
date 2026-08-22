# -*- coding: utf-8 -*-
"""تست‌های آفلاین فاز ۳ — محدودکننده نرخ، قطع‌کننده مدار، تشخیص کپچا، سهمیه، پیام."""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from marketing_divar.client import (DivarBlockedError, DivarClient,  # noqa: E402
                                    looks_like_captcha)
from marketing_divar.db import bump_quota, connect, upsert_lead, quota_today  # noqa: E402
from marketing_divar.messaging import build_message  # noqa: E402
from marketing_divar.rate import CircuitBreaker, RateLimiter  # noqa: E402


class TestCaptchaDetection(unittest.TestCase):
    def test_markers(self):
        self.assertTrue(looks_like_captcha('{"error":"captcha_required"}'))
        self.assertTrue(looks_like_captcha("Please solve the Puzzle"))
        self.assertFalse(looks_like_captcha('{"phone_number":"0912"}'))

    def _client_with(self, status, body):
        cl = DivarClient.__new__(DivarClient)
        cl.session_path = "data/x.json"
        cl.token = "t"
        cl.limiter = MagicMock()
        cl.base = "https://api.divar.ir"
        r = MagicMock()
        r.status_code = status
        r.text = body
        cl.http = MagicMock()
        cl.http.get.return_value = r
        return cl

    def test_429_raises_block(self):
        cl = self._client_with(429, "too many requests")
        with self.assertRaises(DivarBlockedError):
            cl.get_phone("tok")

    def test_403_captcha_raises_block(self):
        cl = self._client_with(403, "captcha challenge required")
        with self.assertRaises(DivarBlockedError):
            cl.get_phone("tok")

    def test_200_captcha_body_raises_block(self):
        # چالش کپچا گاهی با کد 200 می‌آید — باید تشخیص داده شود
        r = MagicMock()
        r.status_code = 200
        r.text = '{"widget_list": null, "error": "captcha"}'

        def raise_valueerror(*a, **k):
            raise ValueError("no json")
        r.json.side_effect = raise_valueerror
        cl = DivarClient.__new__(DivarClient)
        cl.session_path = "data/x.json"
        cl.token = "t"
        cl.limiter = MagicMock()
        cl.base = "https://api.divar.ir"
        cl.http = MagicMock()
        cl.http.get.return_value = r
        with self.assertRaises(DivarBlockedError):
            cl.get_phone("tok")


class TestCircuitBreaker(unittest.TestCase):
    def test_trip_opens_and_backoff(self):
        now = [1000.0]
        slept = []
        br = CircuitBreaker(cooldown_min=30, backoff_mult=2.0, max_consecutive=3,
                            clock=lambda: now[0], sleeper=lambda s: slept.append(s))
        s1 = br.trip("first")
        self.assertAlmostEqual(s1, 30 * 60)          # اولین: ۳۰ دقیقه
        self.assertTrue(br.is_open())
        s2 = br.trip("second")                        # دومی: ۶۰ دقیقه
        self.assertAlmostEqual(s2, 60 * 60)
        self.assertTrue(br.is_open())
        self.assertFalse(br.is_fatal())

    def test_fatal_after_max(self):
        now = [0.0]
        br = CircuitBreaker(max_consecutive=3, clock=lambda: now[0])
        for _ in range(3):
            br.trip()
        self.assertTrue(br.is_fatal())

    def test_reset_on_success(self):
        br = CircuitBreaker(max_consecutive=3, clock=lambda: 0.0)
        br.trip()
        br.trip()
        br.reset()
        self.assertFalse(br.is_open())
        self.assertFalse(br.is_fatal())


class TestRateLimiter(unittest.TestCase):
    def test_min_interval_enforced(self):
        rl = RateLimiter(phone_delay=0.05, search_delay=0.01, jitter=0.0)
        import time as _t
        t0 = _t.monotonic()
        rl.wait("phone")
        rl.wait("phone")  # باید ~0.05s صبر کند
        self.assertGreaterEqual(_t.monotonic() - t0, 0.05)

    def test_slow_down_multiplies(self):
        rl = RateLimiter(phone_delay=10, jitter=0)
        rl.slow_down(1.5)
        rl.slow_down(1.5)
        self.assertEqual(rl._min["phone"], 22.5)  # 10*1.5*1.5


class TestQuota(unittest.TestCase):
    def test_daily_quota_counter(self):
        tmp = tempfile.mkdtemp()
        con = connect(os.path.join(tmp, "q.db"))
        upsert_lead(con, {"token": "t1", "title": "x", "subtitle": "",
                          "url": "u", "has_chat": 1}, "kw", "iran")
        self.assertEqual(quota_today(con)["phones"], 0)
        bump_quota(con, "phones")
        bump_quota(con, "phones")
        self.assertEqual(quota_today(con)["phones"], 2)
        con.close()


class TestMessaging(unittest.TestCase):
    def test_personalization(self):
        lead = {"title": "آپارتمان ۸۰ متری", "subtitle": "ودیعه ۵۰۰", "url": "u"}
        msg = build_message("آگهی «{title}» — {subtitle}", lead)
        self.assertIn("آپارتمان ۸۰ متری", msg)
        self.assertIn("ودیعه ۵۰۰", msg)

    def test_no_crash_on_empty(self):
        msg = build_message("«{title}»", {"title": None, "subtitle": None, "url": ""})
        self.assertIn("آگهی شما", msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
