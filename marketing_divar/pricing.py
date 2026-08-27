# -*- coding: utf-8 -*-
"""استخراج قیمت آگهی دیوار (تومان) و تطبیق بازه."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

_DIGIT = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _digits(text: str) -> str:
    t = (text or "").translate(_DIGIT)
    t = t.replace("٬", "").replace(",", "").replace(" ", "")
    return t


def parse_toman(text: Any) -> Optional[int]:
    """قیمت به تومان. JSON-LD دیوار معمولاً ریال است."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        n = int(text)
        if n <= 0:
            return None
        # اعداد خیلی بزرگ در اسکیما معمولاً ریال‌اند
        return n // 10 if n >= 10_000_000_000 else n
    raw = str(text).translate(_DIGIT)
    if not raw.strip():
        return None
    # میلیارد
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*میلیارد", raw)
    if m:
        return int(float(m.group(1).replace(",", ".")) * 1_000_000_000)
    # میلیون
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*میلیون", raw)
    if m:
        return int(float(m.group(1).replace(",", ".")) * 1_000_000)
    # تومان با رقم
    m = re.search(r"([\d٬,]{3,})\s*تومان", raw)
    if m:
        n = int(re.sub(r"\D", "", m.group(1)) or "0")
        return n or None
    # فقط رقم بزرگ در متن قیمت
    m = re.search(r"([\d٬,]{5,})", raw)
    if m:
        n = int(re.sub(r"\D", "", m.group(1)) or "0")
        if n >= 10_000:
            return n // 10 if n >= 10_000_000_000 else n
    return None


def price_from_post(post: Dict[str, Any]) -> Optional[int]:
    if post.get("price"):
        try:
            n = int(post["price"])
            if n > 0:
                return n
        except (TypeError, ValueError):
            pass
    blob = " ".join(str(post.get(k) or "") for k in
                    ("title", "subtitle", "top", "bottom", "description", "price_text"))
    return parse_toman(blob)


def in_range(price: Optional[int], min_toman: int = 0, max_toman: int = 0) -> bool:
    """اگر بازه خالی باشد همه قبول‌اند. اگر بازه هست و قیمت نیست → رد."""
    if not min_toman and not max_toman:
        return True
    if price is None or price <= 0:
        return False
    if min_toman and price < min_toman:
        return False
    if max_toman and price > max_toman:
        return False
    return True


def million_to_toman(m: Any) -> int:
    try:
        v = float(str(m).translate(_DIGIT).replace(",", "."))
    except (TypeError, ValueError):
        return 0
    if v <= 0:
        return 0
    return int(v * 1_000_000)
