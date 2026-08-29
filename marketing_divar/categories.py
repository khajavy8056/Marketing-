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
# parent خالی = دستهٔ اصلی؛ پر = زیر‌دسته
CATEGORIES: List[Dict[str, str]] = [
    {"slug": "", "group": "", "title": "همه دسته‌ها", "parent": ""},
    {"slug": "real-estate", "group": "املاک", "title": "املاک (همه)", "parent": ""},
    {"slug": "apartment-sell", "group": "املاک", "title": "فروش آپارتمان", "parent": "real-estate"},
    {"slug": "apartment-rent", "group": "املاک", "title": "اجاره آپارتمان", "parent": "real-estate"},
    {"slug": "house-villa-sell", "group": "املاک", "title": "فروش خانه و ویلا", "parent": "real-estate"},
    {"slug": "house-villa-rent", "group": "املاک", "title": "اجاره خانه و ویلا", "parent": "real-estate"},
    {"slug": "office-sell", "group": "املاک", "title": "فروش دفتر و مغازه", "parent": "real-estate"},
    {"slug": "office-rent", "group": "املاک", "title": "اجاره دفتر و مغازه", "parent": "real-estate"},
    {"slug": "plot-old", "group": "املاک", "title": "زمین و باغ", "parent": "real-estate"},
    {"slug": "rent-temporary", "group": "املاک", "title": "اجاره کوتاه‌مدت", "parent": "real-estate"},
    {"slug": "vehicles", "group": "وسایل نقلیه", "title": "وسایل نقلیه (همه)", "parent": ""},
    {"slug": "light", "group": "وسایل نقلیه", "title": "خودرو سواری", "parent": "vehicles"},
    {"slug": "motorcycles", "group": "وسایل نقلیه", "title": "موتورسیکلت", "parent": "vehicles"},
    {"slug": "auto-parts-accessories", "group": "وسایل نقلیه", "title": "قطعات یدکی خودرو", "parent": "vehicles"},
    {"slug": "truck", "group": "وسایل نقلیه", "title": "سنگین و نیمه‌سنگین", "parent": "vehicles"},
    {"slug": "rental-car", "group": "وسایل نقلیه", "title": "اجاره خودرو", "parent": "vehicles"},
    {"slug": "classic-car", "group": "وسایل نقلیه", "title": "کلاسیک", "parent": "vehicles"},
    {"slug": "electronic-devices", "group": "کالای دیجیتال", "title": "کالای دیجیتال (همه)", "parent": ""},
    {"slug": "mobile-tablet", "group": "کالای دیجیتال", "title": "موبایل و تبلت (همه)", "parent": "electronic-devices"},
    {"slug": "mobile-phones", "group": "کالای دیجیتال", "title": "موبایل", "parent": "mobile-tablet"},
    {"slug": "tablet", "group": "کالای دیجیتال", "title": "تبلت", "parent": "mobile-tablet"},
    {"slug": "mobile-tablet-accessories", "group": "کالای دیجیتال", "title": "لوازم جانبی موبایل", "parent": "mobile-tablet"},
    {"slug": "computers", "group": "کالای دیجیتال", "title": "رایانه", "parent": "electronic-devices"},
    {"slug": "laptops", "group": "کالای دیجیتال", "title": "لپ‌تاپ", "parent": "computers"},
    {"slug": "game-consoles-and-video-games", "group": "کالای دیجیتال", "title": "کنسول و بازی", "parent": "electronic-devices"},
    {"slug": "audio-video", "group": "کالای دیجیتال", "title": "صوتی و تصویری", "parent": "electronic-devices"},
    {"slug": "home-kitchen", "group": "خانه", "title": "خانه و آشپزخانه (همه)", "parent": ""},
    {"slug": "furniture-wood", "group": "خانه", "title": "مبلمان و صنایع چوب", "parent": "home-kitchen"},
    {"slug": "refrigerator-freezer", "group": "خانه", "title": "یخچال و فریزر", "parent": "home-kitchen"},
    {"slug": "services", "group": "خدمات", "title": "خدمات", "parent": ""},
    {"slug": "jobs", "group": "استخدام", "title": "استخدام و کاریابی", "parent": ""},
    {"slug": "personal", "group": "شخصی", "title": "وسایل شخصی (همه)", "parent": ""},
    {"slug": "clothing-and-shoes", "group": "شخصی", "title": "پوشاک و کفش", "parent": "personal"},
    {"slug": "entertainment", "group": "سرگرمی", "title": "سرگرمی و فراغت", "parent": ""},
    {"slug": "social-services", "group": "اجتماعی", "title": "اجتماعی", "parent": ""},
    {"slug": "tools-materials-equipment", "group": "تجهیزات", "title": "تجهیزات و صنعتی", "parent": ""},
    {"slug": "animals", "group": "حیوانات", "title": "حیوانات (همه)", "parent": ""},
    {"slug": "cats", "group": "حیوانات", "title": "گربه", "parent": "animals"},
    {"slug": "dogs", "group": "حیوانات", "title": "سگ", "parent": "animals"},
    {"slug": "birds", "group": "حیوانات", "title": "پرنده", "parent": "animals"},
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
    out: List[Dict[str, str]] = []
    for c in CATEGORIES:
        d = dict(c)
        if c.get("parent"):
            d["label"] = " └ " + c["title"]
        else:
            d["label"] = c["title"]
        out.append(d)
    return out
