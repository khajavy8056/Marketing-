# -*- coding: utf-8 -*-
"""دسته‌بندی‌های عمومی دیوار — همان اسلاگ‌های صفحهٔ /s/{شهر}/{دسته}.

بدون لاگین کار می‌کند (مثل جستجوی HTML). کلمهٔ کلیدی اختیاری است:
  فقط دسته  → همهٔ آگهی‌های آن دسته
  دسته+کلمه → جستجو داخل همان دسته
  فقط کلمه  → رفتار قبلی (کل سایت)
"""

from __future__ import annotations

from typing import Dict, List, Optional

# اسلاگ‌ها از URL عمومی دیوار (divar.ir/s/tehran/<slug>)
CATEGORIES: List[Dict[str, str]] = [
    {"slug": "", "group": "", "title": "همه دسته‌ها"},
    {"slug": "real-estate", "group": "املاک", "title": "املاک (همه)"},
    {"slug": "apartment-sell", "group": "املاک", "title": "فروش آپارتمان"},
    {"slug": "apartment-rent", "group": "املاک", "title": "اجاره آپارتمان"},
    {"slug": "house-villa-sell", "group": "املاک", "title": "فروش خانه و ویلا"},
    {"slug": "house-villa-rent", "group": "املاک", "title": "اجاره خانه و ویلا"},
    {"slug": "office-sell", "group": "املاک", "title": "فروش دفتر و مغازه"},
    {"slug": "office-rent", "group": "املاک", "title": "اجاره دفتر و مغازه"},
    {"slug": "vehicles", "group": "وسایل نقلیه", "title": "وسایل نقلیه (همه)"},
    {"slug": "light", "group": "وسایل نقلیه", "title": "خودرو سواری"},
    {"slug": "motorcycles", "group": "وسایل نقلیه", "title": "موتورسیکلت"},
    {"slug": "auto-parts-accessories", "group": "وسایل نقلیه", "title": "قطعات یدکی خودرو"},
    {"slug": "truck", "group": "وسایل نقلیه", "title": "سنگین و نیمه‌سنگین"},
    {"slug": "rental-car", "group": "وسایل نقلیه", "title": "اجاره خودرو"},
    {"slug": "electronic-devices", "group": "کالای دیجیتال", "title": "کالای دیجیتال (همه)"},
    {"slug": "mobile-tablet", "group": "کالای دیجیتال", "title": "موبایل و تبلت"},
    {"slug": "computers", "group": "کالای دیجیتال", "title": "رایانه"},
    {"slug": "game-consoles-and-video-games", "group": "کالای دیجیتال", "title": "کنسول و بازی"},
    {"slug": "audio-video", "group": "کالای دیجیتال", "title": "صوتی و تصویری"},
    {"slug": "home-kitchen", "group": "خانه", "title": "خانه و آشپزخانه"},
    {"slug": "services", "group": "خدمات", "title": "خدمات"},
    {"slug": "jobs", "group": "استخدام", "title": "استخدام و کاریابی"},
    {"slug": "personal", "group": "شخصی", "title": "وسایل شخصی"},
    {"slug": "entertainment", "group": "سرگرمی", "title": "سرگرمی و فراغت"},
    {"slug": "social-services", "group": "اجتماعی", "title": "اجتماعی"},
    {"slug": "tools-materials-equipment", "group": "تجهیزات", "title": "تجهیزات و صنعتی"},
    {"slug": "animals", "group": "حیوانات", "title": "حیوانات"},
]

_BY_SLUG = {c["slug"]: c for c in CATEGORIES if c["slug"]}


def normalize_slug(raw: Optional[str]) -> str:
    s = (raw or "").strip().lower().strip("/")
    if not s or s in ("all", "none", "-"):
        return ""
    if s in _BY_SLUG:
        return s
    return ""


def title_of(slug: Optional[str]) -> str:
    s = normalize_slug(slug)
    if not s:
        return ""
    return _BY_SLUG[s]["title"]


def public_list() -> List[Dict[str, str]]:
    return [dict(c) for c in CATEGORIES]
