# -*- coding: utf-8 -*-
"""محدودکننده نرخ + قطع‌کننده مدار — قلب استراتژی «بلاک نشدن».

لایه ۱ (RateLimiter): تاخیر حداقلی + جیتر تصادفی بین درخواست‌ها → زیر آستانه دیوار.
لایه ۲ (CircuitBreaker): اولین نشانه بلاک/کپچا → توقف خودکار و بازگشت کندتر.
"""

from __future__ import annotations

import random
import time
from typing import Dict, Optional


class RateLimiter:
    """تاخیر انسانی‌گونه بین انواع درخواست."""

    def __init__(self, phone_delay: float = 10.0, search_delay: float = 5.0,
                 page_delay: float = 8.0, jitter: float = 4.0):
        self._min = {"phone": phone_delay, "search": search_delay, "page": page_delay}
        self._jitter = jitter
        self._last: Dict[str, float] = {}

    def wait(self, kind: str) -> None:
        """قبل از هر درخواست صدا زده شود؛ حداقل فاصله را تضمین می‌کند."""
        base = self._min.get(kind, 5.0)
        elapsed = time.monotonic() - self._last.get(kind, 0.0)
        remaining = base - elapsed
        if remaining > 0:
            time.sleep(remaining + random.uniform(0, self._jitter))
        else:
            time.sleep(random.uniform(0, min(1.0, self._jitter)))
        self._last[kind] = time.monotonic()

    def slow_down(self, multiplier: float) -> None:
        """بعد از هر بلاک، همه فاصله‌ها را ضرب می‌کند (بازگشت محافظه‌کارانه)."""
        for k in self._min:
            self._min[k] = round(self._min[k] * multiplier, 1)


class CircuitBreaker:
    """سه وضعیت: CLOSED (عادی) / OPEN (در سرد بودن) / FATAL (توقف تا فردا)."""

    def __init__(self, cooldown_min: float = 30, backoff_mult: float = 1.5,
                 max_consecutive: int = 3, clock=time.monotonic, sleeper=time.sleep):
        self.cooldown_min = cooldown_min
        self.backoff_mult = backoff_mult
        self.max_consecutive = max_consecutive
        self.consecutive = 0
        self.open_until: float = 0.0
        self.last_reason: str = ""
        self._clock = clock
        self._sleep = sleeper

    # --- وضعیت ---
    def is_open(self) -> bool:
        return self._clock() < self.open_until

    def is_fatal(self) -> bool:
        return self.consecutive >= self.max_consecutive

    def seconds_remaining(self) -> float:
        return max(0.0, self.open_until - self._clock())

    # --- رخدادها ---
    def trip(self, reason: str = "") -> float:
        """ثبت یک بلاک؛ مدت سردشدن بعدی را برمی‌گرداند (ثانیه)."""
        self.consecutive += 1
        self.last_reason = reason
        minutes = self.cooldown_min * (self.backoff_mult ** (self.consecutive - 1))
        self.open_until = self._clock() + minutes * 60
        return minutes * 60

    def reset(self) -> None:
        self.consecutive = 0
        self.open_until = 0.0

    def wait_cooldown(self, on_tick=None) -> None:
        """صبر تا پایان سردشدن (برای حالت غیرتعاملی)."""
        while self.is_open():
            remaining = int(self.seconds_remaining()) + 1
            if on_tick:
                on_tick(remaining)
            self._sleep(min(remaining, 30))
