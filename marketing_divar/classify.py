# -*- coding: utf-8 -*-
"""طبقه‌بندی آگهی: خریدار، معیوب، جای‌نگهدار، نوع قیمت.

شکارچی و ویژه فقط روی نقد سالم کار می‌کنند. این لایه قبل از امتیاز است.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from .matching import normalize
from .pricing import parse_toman

_BUYER = (
    "خریدار", "میخرم", "می‌خرم", "ميخرم", "خرید نقد", "خریدار",
    "خرید گوشی", "خریدار گوشی", "خریدار گوشی", "نیازمند خرید",
)
_DEFECT = (
    "معیوب", "معيوب", "شکسته", "اوراق", "اوراقی", "تعمیری", "تعمیر میخواد",
    "نیاز به تعمیر", "نیازمند تعمیر", "ال سی دی شکسته", "ال‌سی‌دی شکسته",
    "صفحه شکسته", "آب خورده", "آبخورده", "افتاده", "خط و خش زیاد",
    "برای قطعه", "برای قطعات", "لاشه", "نیمه اوراق",
)
_NEGOTIABLE = ("توافقی", "توافقى", "قیمت توافقی", "قیمتتوافقی")
_INSTALLMENT = ("اقساط", "قسطی", "پیش پرداخت")
_SWAP = ("معاوضه", "تهاتر", "عوض میکنم")
_PLACEHOLDER_WORDS = ("هزار تومن بذار", "قیمت الکی", "یه تومن", "۱۰۰۰ تومن")


def _blob(post: Dict[str, Any]) -> str:
    parts = [post.get("title"), post.get("subtitle"), post.get("description"),
             post.get("top"), post.get("bottom"), post.get("price_text"),
             post.get("condition"), post.get("status_text")]
    return " ".join(str(p) for p in parts if p)


def is_buyer(text: str) -> bool:
    n = normalize(text)
    return any(normalize(w) in n for w in _BUYER)


def is_defect(text: str, status_field: str = "") -> bool:
    st = normalize(status_field)
    if st and any(x in st for x in ("معیوب", "معيوب", "تعمیری", "شکسته", "اوراق")):
        return True
    n = normalize(text)
    return any(normalize(w) in n for w in _DEFECT)


def price_kind_of(post: Dict[str, Any], price: Optional[int] = None) -> str:
    blob = _blob(post)
    n = normalize(blob)
    if is_buyer(blob):
        return "buyer"
    if any(normalize(w) in n for w in _SWAP):
        return "swap"
    if any(normalize(w) in n for w in _INSTALLMENT):
        return "installment"
    if any(normalize(w) in n for w in _NEGOTIABLE) and not (price and price > 0):
        return "negotiable"
    if price and price > 0:
        return "cash"
    if any(normalize(w) in n for w in _NEGOTIABLE):
        return "negotiable"
    return "unknown"


def is_placeholder(price: Optional[int], kind: str, category: str = "") -> bool:
    """قیمت نمایشی مثل ۱۰۰۰ / ۱۱ / خیلی کوچک نسبت به دسته."""
    if kind in ("negotiable", "unknown", "buyer", "swap"):
        return False
    if not price or price <= 0:
        return False
    if price in (1, 11, 111, 1000, 1111, 10000):
        return True
    cat = (category or "").lower()
    if "mobile" in cat or "phone" in cat or "laptop" in cat:
        if price < 500_000:
            return True
    if cat in ("light", "vehicles") or "car" in cat:
        if 0 < price < 5_000_000:
            return True
    return False


def classify_post(post: Dict[str, Any], category: str = "") -> Dict[str, Any]:
    blob = _blob(post)
    status_field = str(post.get("condition") or post.get("status_text") or "")
    price = post.get("price")
    if not isinstance(price, int):
        price = parse_toman(price) or parse_toman(blob)
    buyer = is_buyer(blob)
    defect = is_defect(blob, status_field)
    kind = "buyer" if buyer else price_kind_of(post, price)
    placeholder = is_placeholder(price, kind, category)
    inquiry = (kind in ("negotiable", "unknown") and not buyer and not defect)
    if placeholder:
        inquiry = True
        kind = "placeholder" if kind == "cash" else kind
    return {
        "price_toman": int(price or 0),
        "price_kind": kind,
        "is_buyer": buyer,
        "is_defect": defect,
        "is_placeholder": placeholder,
        "needs_inquiry": bool(inquiry and not buyer),
        "reject": buyer,
    }
