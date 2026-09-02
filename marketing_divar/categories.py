# -*- coding: utf-8 -*-
"""دسته‌بندی واحد برنامه — همان درخت دیوار.

شیپور اسلاگ جدا دارد؛ با انتخاب کاربر به‌صورت خودکار نگاشت می‌شود.
درخت جدا برای هر سایت ساخته نمی‌شود.
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
    {"slug": "shop-sell", "group": "املاک", "title": "فروش مغازه", "parent": "real-estate"},
    {"slug": "shop-rent", "group": "املاک", "title": "اجاره مغازه", "parent": "real-estate"},
    {"slug": "plot-old", "group": "املاک", "title": "زمین و باغ", "parent": "real-estate"},
    {"slug": "industry-agriculture-business-sell", "group": "املاک", "title": "فروش صنعتی و کشاورزی", "parent": "real-estate"},
    {"slug": "industry-agriculture-business-rent", "group": "املاک", "title": "اجاره صنعتی و کشاورزی", "parent": "real-estate"},
    {"slug": "rent-temporary", "group": "املاک", "title": "اجاره کوتاه‌مدت", "parent": "real-estate"},
    {"slug": "vehicles", "group": "وسایل نقلیه", "title": "وسایل نقلیه (همه)", "parent": ""},
    {"slug": "light", "group": "وسایل نقلیه", "title": "خودرو سواری", "parent": "vehicles"},
    {"slug": "motorcycles", "group": "وسایل نقلیه", "title": "موتورسیکلت", "parent": "vehicles"},
    {"slug": "auto-parts-accessories", "group": "وسایل نقلیه", "title": "قطعات یدکی خودرو", "parent": "vehicles"},
    {"slug": "truck", "group": "وسایل نقلیه", "title": "سنگین و نیمه‌سنگین", "parent": "vehicles"},
    {"slug": "rental-car", "group": "وسایل نقلیه", "title": "اجاره خودرو", "parent": "vehicles"},
    {"slug": "classic-car", "group": "وسایل نقلیه", "title": "کلاسیک", "parent": "vehicles"},
    {"slug": "heavy-vehicles", "group": "وسایل نقلیه", "title": "ماشین‌آلات سنگین", "parent": "vehicles"},
    {"slug": "boat", "group": "وسایل نقلیه", "title": "قایق و جت‌اسکی", "parent": "vehicles"},
    {"slug": "electronic-devices", "group": "کالای دیجیتال", "title": "کالای دیجیتال (همه)", "parent": ""},
    {"slug": "mobile-tablet", "group": "کالای دیجیتال", "title": "موبایل و تبلت (همه)", "parent": "electronic-devices"},
    {"slug": "mobile-phones", "group": "کالای دیجیتال", "title": "موبایل", "parent": "mobile-tablet"},
    {"slug": "apple", "group": "کالای دیجیتال", "title": "آیفون / اپل", "parent": "mobile-phones"},
    {"slug": "samsung", "group": "کالای دیجیتال", "title": "سامسونگ", "parent": "mobile-phones"},
    {"slug": "xiaomi", "group": "کالای دیجیتال", "title": "شیائومی", "parent": "mobile-phones"},
    {"slug": "huawei", "group": "کالای دیجیتال", "title": "هواوی", "parent": "mobile-phones"},
    {"slug": "nokia", "group": "کالای دیجیتال", "title": "نوکیا", "parent": "mobile-phones"},
    {"slug": "honor", "group": "کالای دیجیتال", "title": "آنر", "parent": "mobile-phones"},
    {"slug": "motorola", "group": "کالای دیجیتال", "title": "موتورولا", "parent": "mobile-phones"},
    {"slug": "google-pixel", "group": "کالای دیجیتال", "title": "گوگل پیکسل", "parent": "mobile-phones"},
    {"slug": "oneplus", "group": "کالای دیجیتال", "title": "وان‌پلاس", "parent": "mobile-phones"},
    {"slug": "nothing", "group": "کالای دیجیتال", "title": "ناتینگ", "parent": "mobile-phones"},
    {"slug": "sony", "group": "کالای دیجیتال", "title": "سونی موبایل", "parent": "mobile-phones"},
    {"slug": "lg", "group": "کالای دیجیتال", "title": "ال‌جی", "parent": "mobile-phones"},
    {"slug": "oppo", "group": "کالای دیجیتال", "title": "اوپو", "parent": "mobile-phones"},
    {"slug": "vivo", "group": "کالای دیجیتال", "title": "ویوو", "parent": "mobile-phones"},
    {"slug": "realme", "group": "کالای دیجیتال", "title": "ریلمی", "parent": "mobile-phones"},
    {"slug": "tablet", "group": "کالای دیجیتال", "title": "تبلت", "parent": "mobile-tablet"},
    {"slug": "mobile-tablet-accessories", "group": "کالای دیجیتال", "title": "لوازم جانبی موبایل", "parent": "mobile-tablet"},
    {"slug": "computers", "group": "کالای دیجیتال", "title": "رایانه", "parent": "electronic-devices"},
    {"slug": "laptops", "group": "کالای دیجیتال", "title": "لپ‌تاپ", "parent": "computers"},
    {"slug": "macbook", "group": "کالای دیجیتال", "title": "مک‌بوک", "parent": "laptops"},
    {"slug": "asus-laptop", "group": "کالای دیجیتال", "title": "لپ‌تاپ ایسوس", "parent": "laptops"},
    {"slug": "lenovo-laptop", "group": "کالای دیجیتال", "title": "لپ‌تاپ لنوو", "parent": "laptops"},
    {"slug": "hp-laptop", "group": "کالای دیجیتال", "title": "لپ‌تاپ اچ‌پی", "parent": "laptops"},
    {"slug": "dell-laptop", "group": "کالای دیجیتال", "title": "لپ‌تاپ دل", "parent": "laptops"},
    {"slug": "acer-laptop", "group": "کالای دیجیتال", "title": "لپ‌تاپ ایسر", "parent": "laptops"},
    {"slug": "msi-laptop", "group": "کالای دیجیتال", "title": "لپ‌تاپ ام‌اس‌آی", "parent": "laptops"},
    {"slug": "desktop-computers", "group": "کالای دیجیتال", "title": "رایانه رومیزی", "parent": "computers"},
    {"slug": "computer-and-laptop-accessories", "group": "کالای دیجیتال", "title": "لوازم جانبی رایانه", "parent": "computers"},
    {"slug": "game-consoles-and-video-games", "group": "کالای دیجیتال", "title": "کنسول و بازی", "parent": "electronic-devices"},
    {"slug": "audio-video", "group": "کالای دیجیتال", "title": "صوتی و تصویری", "parent": "electronic-devices"},
    {"slug": "camera-camcoders", "group": "کالای دیجیتال", "title": "دوربین", "parent": "electronic-devices"},
    {"slug": "telephone", "group": "کالای دیجیتال", "title": "تلفن رومیزی", "parent": "electronic-devices"},
    {"slug": "home-kitchen", "group": "خانه", "title": "خانه و آشپزخانه (همه)", "parent": ""},
    {"slug": "furniture-wood", "group": "خانه", "title": "مبلمان و صنایع چوب", "parent": "home-kitchen"},
    {"slug": "refrigerator-freezer", "group": "خانه", "title": "یخچال و فریزر", "parent": "home-kitchen"},
    {"slug": "washers", "group": "خانه", "title": "ماشین لباسشویی", "parent": "home-kitchen"},
    {"slug": "vacuum-cleaner", "group": "خانه", "title": "جاروبرقی", "parent": "home-kitchen"},
    {"slug": "cookware", "group": "خانه", "title": "ظروف آشپزخانه", "parent": "home-kitchen"},
    {"slug": "lighting", "group": "خانه", "title": "روشنایی", "parent": "home-kitchen"},
    {"slug": "carpet", "group": "خانه", "title": "فرش و گلیم", "parent": "home-kitchen"},
    {"slug": "curtains-tablecloths", "group": "خانه", "title": "پرده و رومیزی", "parent": "home-kitchen"},
    {"slug": "bathroom-accessories", "group": "خانه", "title": "سرویس بهداشتی", "parent": "home-kitchen"},
    {"slug": "heating-cooling", "group": "خانه", "title": "سرمایش و گرمایش", "parent": "home-kitchen"},
    {"slug": "decorative", "group": "خانه", "title": "تزئینی", "parent": "home-kitchen"},
    {"slug": "services", "group": "خدمات", "title": "خدمات", "parent": ""},
    {"slug": "jobs", "group": "استخدام", "title": "استخدام و کاریابی", "parent": ""},
    {"slug": "personal", "group": "شخصی", "title": "وسایل شخصی (همه)", "parent": ""},
    {"slug": "clothing-and-shoes", "group": "شخصی", "title": "پوشاک و کفش", "parent": "personal"},
    {"slug": "bags-shoes", "group": "شخصی", "title": "کیف و کفش", "parent": "personal"},
    {"slug": "jewelry", "group": "شخصی", "title": "زیورآلات", "parent": "personal"},
    {"slug": "health-beauty", "group": "شخصی", "title": "آرایشی و بهداشتی", "parent": "personal"},
    {"slug": "child-baby", "group": "شخصی", "title": "کودک و نوزاد", "parent": "personal"},
    {"slug": "entertainment", "group": "سرگرمی", "title": "سرگرمی و فراغت", "parent": ""},
    {"slug": "ticket", "group": "سرگرمی", "title": "بلیت", "parent": "entertainment"},
    {"slug": "tour-travel", "group": "سرگرمی", "title": "تور و سفر", "parent": "entertainment"},
    {"slug": "book-student", "group": "سرگرمی", "title": "کتاب و لوازم‌تحریر", "parent": "entertainment"},
    {"slug": "sport", "group": "سرگرمی", "title": "ورزش", "parent": "entertainment"},
    {"slug": "bicycle", "group": "سرگرمی", "title": "دوچرخه", "parent": "entertainment"},
    {"slug": "musical-instruments", "group": "سرگرمی", "title": "آلات موسیقی", "parent": "entertainment"},
    {"slug": "social-services", "group": "اجتماعی", "title": "اجتماعی", "parent": ""},
    {"slug": "tools-materials-equipment", "group": "تجهیزات", "title": "تجهیزات و صنعتی", "parent": ""},
    {"slug": "industrial-machinery", "group": "تجهیزات", "title": "ماشین‌آلات صنعتی", "parent": "tools-materials-equipment"},
    {"slug": "building-equipment", "group": "تجهیزات", "title": "تجهیزات ساختمانی", "parent": "tools-materials-equipment"},
    {"slug": "animals", "group": "حیوانات", "title": "حیوانات (همه)", "parent": ""},
    {"slug": "cats", "group": "حیوانات", "title": "گربه", "parent": "animals"},
    {"slug": "dogs", "group": "حیوانات", "title": "سگ", "parent": "animals"},
    {"slug": "birds", "group": "حیوانات", "title": "پرنده", "parent": "animals"},
    {"slug": "fish", "group": "حیوانات", "title": "ماهی", "parent": "animals"},
]

_BY_SLUG = {c["slug"]: c for c in CATEGORIES if c["slug"]}

# نگاشت اسلاگ واحد → اسلاگ زنده شیپور
SHEYPOOR_SLUG: Dict[str, str] = {
    "mobile-phones": "mobile-tablet",
    "mobile-tablet": "mobile-tablet",
    "tablet": "mobile-tablet",
    "mobile-tablet-accessories": "mobile-accessories",
    "light": "car",
    "vehicles": "vehicles",
    "motorcycles": "motorcycles",
    "classic-car": "classic-cars",
    "truck": "commercial-cars",
    "heavy-vehicles": "agriculture-construction",
    "auto-parts-accessories": "car-parts",
    "rental-car": "car",
    "boat": "vehicles",
    "real-estate": "real-estate",
    "apartment-sell": "houses-apartments-for-sale",
    "house-villa-sell": "villa-for-sale",
    "apartment-rent": "house-apartment-for-rent",
    "house-villa-rent": "house-apartment-for-rent",
    "office-sell": "office-for-sale",
    "office-rent": "office-for-rent",
    "shop-sell": "shop-for-sale",
    "shop-rent": "shop-for-rent",
    "plot-old": "land",
    "rent-temporary": "short-term-rent",
    "industry-agriculture-business-sell": "industrial-commercial",
    "industry-agriculture-business-rent": "industrial-commercial",
    "electronic-devices": "electronics",
    "computers": "laptop-computer",
    "laptops": "laptop-computer",
    "desktop-computers": "laptop-computer",
    "computer-and-laptop-accessories": "laptop-computer",
    "game-consoles-and-video-games": "video-games-consoles",
    "audio-video": "audio-video",
    "camera-camcoders": "photography",
    "home-kitchen": "home",
    "furniture-wood": "furniture",
    "refrigerator-freezer": "home-appliances",
    "washers": "home-appliances",
    "vacuum-cleaner": "home-appliances",
    "cookware": "home",
    "lighting": "home",
    "carpet": "home",
    "curtains-tablecloths": "home",
    "bathroom-accessories": "home",
    "heating-cooling": "home",
    "decorative": "home",
    "jobs": "jobs",
    "services": "services",
    "personal": "personal-stuff",
    "clothing-and-shoes": "personal-stuff",
    "bags-shoes": "personal-stuff",
    "jewelry": "personal-stuff",
    "health-beauty": "personal-stuff",
    "child-baby": "personal-stuff",
    "entertainment": "sports-games-hobbies",
    "ticket": "sports-games-hobbies",
    "tour-travel": "sports-games-hobbies",
    "book-student": "sports-games-hobbies",
    "sport": "sports-games-hobbies",
    "bicycle": "sports-games-hobbies",
    "musical-instruments": "sports-games-hobbies",
    "social-services": "services",
    "tools-materials-equipment": "industrial-commercial",
    "industrial-machinery": "industrial-commercial",
    "building-equipment": "industrial-commercial",
    "animals": "animals-pet",
    "cats": "animals-pet",
    "dogs": "animals-pet",
    "birds": "animals-pet",
    "fish": "animals-pet",
}


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

def public_list_non_estate() -> List[Dict[str, str]]:
    """لیست بدون املاک — برای پنل نهایی (حوزه املاک کار نمی‌کنیم)."""
    out: List[Dict[str, str]] = []
    for c in CATEGORIES:
        if is_real_estate(c.get("slug")):
            continue
        d = dict(c)
        if c.get("parent"):
            d["label"] = " └ " + c["title"]
        else:
            d["label"] = c["title"]
        out.append(d)
    return out


def platform_slug(canonical: Optional[str], platform: str = "divar") -> str:
    """اسلاگ دستهٔ همان پلتفرم از روی انتخاب واحد کاربر."""
    s = normalize_slug(canonical)
    plat = str(platform or "divar").strip().lower()
    if not s:
        return ""
    if plat == "sheypoor":
        return SHEYPOOR_SLUG.get(s, s)
    return s


def is_vehicle(slug: Optional[str]) -> bool:
    s = normalize_slug(slug)
    if not s:
        return False
    if s in ("vehicles", "light", "motorcycles", "truck", "classic-car",
             "heavy-vehicles", "rental-car", "auto-parts-accessories", "boat"):
        return True
    rec = _BY_SLUG.get(s) or {}
    return rec.get("group") == "وسایل نقلیه" or rec.get("parent") == "vehicles"


PHONE_BRANDS = frozenset({
    "apple", "samsung", "xiaomi", "huawei", "nokia", "honor", "motorola",
    "google-pixel", "oneplus", "nothing", "sony", "lg", "oppo", "vivo", "realme",
})
LAPTOP_BRANDS = frozenset({
    "macbook", "asus-laptop", "lenovo-laptop", "hp-laptop", "dell-laptop",
    "acer-laptop", "msi-laptop",
})


def is_real_estate(slug: Optional[str]) -> bool:
    s = normalize_slug(slug)
    if not s:
        return False
    rec = _BY_SLUG.get(s) or {}
    return rec.get("group") == "املاک" or rec.get("parent") == "real-estate" or s == "real-estate"


def hunter_allowed(slug: Optional[str]) -> bool:
    """املاک شکار نمی‌شود؛ بقیه دسته‌ها مجازند."""
    return not is_real_estate(slug)


def search_slug(canonical: Optional[str], platform: str = "divar") -> str:
    """اسلاگ جستجو: برند موبایل/لپ‌تاپ روی دستهٔ والد می‌رود."""
    s = normalize_slug(canonical)
    if not s:
        return ""
    if s in PHONE_BRANDS:
        s = "mobile-phones"
    elif s in LAPTOP_BRANDS:
        s = "laptops"
    elif s == "vacuum-cleaner":
        s = "home-kitchen"
    return platform_slug(s, platform)


def implied_query(keyword: str = "", category: str = "") -> str:
    """اگر فقط برند انتخاب شده، عنوان برند همان عبارت جستجو است."""
    kw = (keyword or "").strip()
    if kw:
        return kw
    s = normalize_slug(category)
    if s in PHONE_BRANDS or s in LAPTOP_BRANDS:
        return title_of(s)
    return ""
