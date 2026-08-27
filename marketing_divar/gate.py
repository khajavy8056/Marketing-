# -*- coding: utf-8 -*-
"""کپچای سادهٔ خود برنامه — فقط برای تأیید حضور اپراتور داخل پنل.

جایگزین کپچای دیوار نیست؛ دیوار اگر چالش بخواهد باید در مرورگر حل شود.
"""

from __future__ import annotations

import random
from typing import Any, Dict

_FA = "۰۱۲۳۴۵۶۷۸۹"
_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def to_fa(n: int) -> str:
    return "".join(_FA[int(ch)] if ch.isdigit() else ch for ch in str(n))


def new_challenge(account: str) -> Dict[str, Any]:
    a, b = random.randint(3, 9), random.randint(3, 9)
    return {
        "account": account,
        "a": a,
        "b": b,
        "expect": a + b,
        "question": f"{to_fa(a)} + {to_fa(b)}",
    }


def check_answer(challenge: Dict[str, Any], raw: Any) -> bool:
    if not challenge:
        return False
    t = str(raw or "").translate(_EN).strip()
    if not t or not t.lstrip("-").isdigit():
        return False
    try:
        return int(t) == int(challenge.get("expect"))
    except (TypeError, ValueError):
        return False
