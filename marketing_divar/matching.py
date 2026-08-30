# -*- coding: utf-8 -*-
"""تطبیق کلمه‌کلیدی روی عنوان و متن آگهی.

جستجوی دیوار گاهی آگهی‌های مرتبطِ غیر دقیق برمی‌گرداند. این لایه بعد از
Discovery، عنوان/توضیح را نرمال می‌کند و فقط آگهی‌هایی را نگه می‌دارد که
عبارت کاربر واقعاً در متن باشد — هدف: کاهش False Positive.

نرمال‌سازی: ارقام فارسی/عربی، ی/ک عربی، نیم‌فاصله، فاصله‌های اضافه.
عبارت چندکلمه‌ای به‌صورت یک واحد بررسی می‌شود (نه OR تک‌کلمه).
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ی/ك عربی → فارسی؛ ارقام فارسی/عربی → انگلیسی؛ انواع خط تیره
_CHAR_MAP = str.maketrans({
    "ي": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه", "أ": "ا", "إ": "ا", "آ": "ا",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    "\u200c": " ",  # نیم‌فاصله
    "\u200f": " ", "\u200e": " ", "\xa0": " ",
    "–": " ", "—": " ", "-": " ", "_": " ",
})

_SPACE_RE = re.compile(r"\s+")


def normalize(text: Any) -> str:
    """متن را برای مقایسه پایدار نرمال می‌کند."""
    if text is None:
        return ""
    t = str(text).translate(_CHAR_MAP).casefold().strip()
    return _SPACE_RE.sub(" ", t)


def compact(text: str) -> str:
    """نسخه بدون فاصله — برای «تدریس خصوصی» در برابر «تدریس‌خصوصی»."""
    return normalize(text).replace(" ", "")


def search_blob(post: Dict[str, Any]) -> str:
    """متن در دسترس از نتیجه جستجو (بدون درخواست اضافه)."""
    parts = [post.get("title"), post.get("subtitle"), post.get("top"),
             post.get("bottom"), post.get("description")]
    return " ".join(str(p) for p in parts if p)


def extract_description(detail: Any) -> str:
    """استخراج توضیح از پاسخ posts-v2 / ساختارهای مشابه دیوار."""
    if not isinstance(detail, dict):
        return ""
    chunks: List[str] = []

    def take(obj: Any, keys: Sequence[str]) -> None:
        if not isinstance(obj, dict):
            return
        for k in keys:
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                chunks.append(v.strip())

    take(detail, ("description", "title"))
    data = detail.get("data")
    take(data, ("description", "title", "subtitle"))
    if isinstance(data, dict):
        take(data.get("seo"), ("description", "title"))
    take(detail.get("seo"), ("description", "title"))

    widgets = []
    for key in ("widgets", "widget_list"):
        w = detail.get(key)
        if isinstance(w, list):
            widgets.extend(w)
    for sec in detail.get("sections") or []:
        if isinstance(sec, dict):
            for w in sec.get("widgets") or []:
                widgets.append(w)
    for w in widgets:
        wd = (w or {}).get("data") if isinstance(w, dict) else None
        take(wd, ("text", "description", "title", "subtitle"))

    # یکتا، پایدار
    seen, out = set(), []
    for c in chunks:
        n = normalize(c)
        if n and n not in seen:
            seen.add(n)
            out.append(c)
    return "\n".join(out)


def keyword_hits(haystack: str, keyword: str) -> bool:
    """آیا عبارت (چندکلمه‌ای) بعد از نرمال‌سازی در متن هست؟"""
    kw = normalize(keyword)
    if not kw:
        return False
    blob = normalize(haystack)
    if kw in blob:
        return True
    ck, cb = compact(kw), compact(haystack)
    return bool(ck) and ck in cb


def match_keywords(haystack: str, keywords: Iterable[str]) -> List[str]:
    """لیست کلمه‌کلیدی‌هایی که در متن خورده‌اند (ترتیب ورودی حفظ می‌شود)."""
    hits = []
    for kw in keywords:
        k = (kw or "").strip()
        if k and keyword_hits(haystack, k) and k not in hits:
            hits.append(k)
    return hits


def consider_new_lead(con, client, post: Dict[str, Any], keyword: str,
                      city: str, fetch_details: bool = True,
                      match_all: bool = False,
                      price_min: int = 0, price_max: int = 0,
                      vip: bool = False) -> bool:
    """اگر آگهی جدید و منطبق باشد در دیتابیس ذخیره می‌شود. True = درج شد.

    match_all: آگهی از دستهٔ دیوار آمده و فیلتر کلمه لازم نیست.
    اگر بازه قیمت باشد و قیمت آگهی در بازه نباشد (یا خوانده نشود) ذخیره نمی‌شود.
    """
    from .db import lead_exists, upsert_lead
    from .pricing import in_range, price_from_post

    token = post.get("token")
    if not token or lead_exists(con, token):
        return False
    from .platforms import split_token
    plat, nid = split_token(token)
    post = dict(post)
    post.setdefault("platform", plat)
    post.setdefault("native_id", nid)
    if plat != "divar":
        fetch_details = False

    from .classify import classify_post
    price = price_from_post(post)
    post = dict(post)
    if price:
        post["price"] = price
    cls = classify_post(post, category=str(post.get("category") or ""))
    if cls.get("reject") or cls.get("is_buyer"):
        return False
    post["price_kind"] = cls.get("price_kind") or ""
    post["is_defect"] = cls.get("is_defect")
    post["is_placeholder"] = cls.get("is_placeholder")
    post["is_buyer"] = cls.get("is_buyer")
    if cls.get("needs_inquiry"):
        post["inquiry_status"] = "pending"
    try:
        from .listing_inspect import apply_inspect_to_post, inspect_listing
        ins = inspect_listing(post, use_llm=False)
        post = apply_inspect_to_post(post, ins)
    except Exception:
        pass
    if not in_range(price, int(price_min or 0), int(price_max or 0)):
        return False
    if cls.get("is_placeholder") and (price_min or price_max):
        return False

    blob = search_blob(post)
    # دستهٔ دیوار: عنوان/متن مهم نیست — آگهی داخل همان لیست دسته است
    if match_all:
        post = dict(post)
        post["matched_keywords"] = keyword or "دسته"
        post["vip"] = bool(vip)
        post["price"] = price or 0
        if not post.get("published_at"):
            post["published_at"] = post.get("bottom") or ""
        is_new = upsert_lead(con, post, keyword or "دسته", city)
        if is_new:
            try:
                from .events import emit
                from .nlu_memory import remember_listing
                emit("listing_found", {
                    "token": post.get("token") or "",
                    "title": post.get("title") or "",
                    "category": post.get("category") or "",
                    "price": price or 0,
                    "keyword": keyword,
                    "platform": post.get("platform") or "divar",
                    "hunter_level": post.get("hunter_level") or "",
                    "is_defect": bool(post.get("is_defect")),
                })
                remember_listing(post.get("token") or "", post.get("category") or "",
                                 hunter_level=post.get("hunter_level") or "", price=int(price or 0),
                                 is_defect=bool(post.get("is_defect")))
            except Exception:
                pass
        return is_new

    if not (keyword or "").strip():
        hits = [keyword or "دسته"]
    else:
        hits = match_keywords(blob, [keyword])
    desc = post.get("description") or ""

    if not hits and fetch_details and client is not None:
        try:
            detail = client.get_post(token)
            desc = extract_description(detail) or desc
            hits = match_keywords(
                " ".join(filter(None, [post.get("title"), desc])), [keyword])
            pub = None
            if isinstance(detail, dict):
                pub = ((detail.get("data") or {}).get("webinfo") or {}).get("date") \
                    or detail.get("published_at")
                if pub:
                    post["published_at"] = str(pub)
        except Exception:
            return False

    if not hits:
        return False

    post = dict(post)
    post["description"] = desc
    post["matched_keywords"] = ",".join(hits)
    post["vip"] = bool(vip)
    post["price"] = price or 0
    if not post.get("published_at"):
        post["published_at"] = post.get("bottom") or ""
    is_new = upsert_lead(con, post, keyword, city)
    if is_new:
        try:
            from .events import emit
            from .nlu_memory import remember_listing
            emit("listing_found", {
                "token": post.get("token") or "",
                "title": post.get("title") or "",
                "category": post.get("category") or "",
                "price": price or 0,
                "keyword": keyword,
                "platform": post.get("platform") or "divar",
                "hunter_level": post.get("hunter_level") or "",
                "is_defect": bool(post.get("is_defect")),
            })
            remember_listing(post.get("token") or "", post.get("category") or "",
                             hunter_level=post.get("hunter_level") or "", price=int(price or 0),
                             is_defect=bool(post.get("is_defect")))
        except Exception:
            pass
    return is_new
