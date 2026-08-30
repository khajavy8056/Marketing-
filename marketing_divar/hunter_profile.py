# -*- coding: utf-8 -*-
"""پروفایل شکارچی هر دسته — افت قیمت، اسلات، سؤال جای‌خالی.

املاک شکار نمی‌شود. پیش‌فرض‌ها نرم‌اند تا دمو چند فرصت پیدا کند.
کاربر در تنظیمات پیشرفته درصدها را سفت می‌کند.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from .matching import normalize

# آستانه‌های نرم — دمو باید چیزی پیدا کند
_SOFT = {"good_pct": 8.0, "great_pct": 15.0, "suspicious_pct": 55.0}


def _adj(key: str, label: str, pct: float, words: List[str],
         ask: bool = False, home_block: bool = False,
         question: str = "") -> Dict[str, Any]:
    return {
        "key": key, "label": label, "pct": float(pct), "words": list(words),
        "ask": ask, "home_block": home_block,
        "question": question or (label + "؟"),
    }


def _vehicle() -> Dict[str, Any]:
    d = dict(_SOFT)
    d.update({
        "family": "vehicle",
        "hunter": True,
        "dealer_mode": False,
        "km_per_year": 20000,
        "slots": [
            {"key": "year", "label": "مدل / سال", "kind": "year",
             "ask": True, "critical": False,
             "question": "مدل و سال دقیق خودرو چیست؟"},
            {"key": "mileage_km", "label": "کارکرد (کیلومتر)", "kind": "int",
             "ask": True, "critical": False,
             "question": "کارکرد واقعی چند کیلومتر است؟"},
            {"key": "chassis", "label": "وضعیت شاسی", "kind": "enum",
             "ask": True, "critical": False,
             "question": "شاسی سالم است یا ضربه/رنگ دارد؟"},
            {"key": "paint", "label": "رنگ بدنه", "kind": "enum",
             "ask": True, "critical": False,
             "question": "بی‌رنگ است یا چند نقطه رنگ دارد (گلگیر/کاپوت/دوررنگ)؟"},
        ],
        "adjustments": [
            _adj("paint_panel", "یک قطعه رنگ (گلگیر / درب / کاپوت)", -2.0,
                 ["گلگیر رنگ", "درب رنگ", "کاپوت رنگ", "صندوق رنگ", "یک لکه رنگ"],
                 question="گلگیر یا کاپوت رنگ دارد؟"),
            _adj("paint_multi", "چند قطعه رنگ", -6.0,
                 ["چند لکه رنگ", "دو رنگ", "سه نقطه رنگ"]),
            _adj("paint_full", "دوررنگ / تمام‌رنگ", -10.0,
                 ["دور رنگ", "دوررنگ", "تمام رنگ", "تمام‌رنگ", "کامل رنگ"]),
            _adj("paint_roof", "سقف رنگ", -6.0, ["سقف رنگ", "سقف رنگ شده"]),
            _adj("chassis_hit", "شاسی ضربه / رنگ شاسی", -10.0,
                 ["شاسی ضربه", "شاسی رنگ", "شاسی خورده", "شاسی چپی",
                  "ستون خورده", "سینی رنگ"],
                 home_block=False),
            _adj("accident", "تصادفی / چپی", -7.0,
                 ["تصادفی", "چپی", "چپ کرده", "اتاق تعویض"]),
            _adj("mechanical", "ایراد موتوری / گیربکس", -7.0,
                 ["تعویض موتور", "موتور تعویض", "گیربکس تعویض",
                  "واشر زده", "یاتاقان", "سیلندر تراش"]),
            _adj("high_km", "کارکرد خیلی بالا (در متن)", -4.0,
                 ["کارکرد بالا", "تاکسی", "پرکار"]),
        ],
    })
    return d


def _phone() -> Dict[str, Any]:
    d = dict(_SOFT)
    d.update({
        "family": "phone",
        "hunter": True,
        "dealer_mode": False,
        "slots": [
            {"key": "storage", "label": "حافظه", "kind": "text",
             "ask": True, "critical": False,
             "question": "حافظه چند گیگ است؟"},
            {"key": "condition", "label": "وضعیت بدنه", "kind": "enum",
             "ask": True, "critical": False,
             "question": "آکبند / در حد نو / خط‌وخش / ترک صفحه؟"},
            {"key": "battery", "label": "باتری", "kind": "text",
             "ask": False, "critical": False,
             "question": "سلامت باتری چقدر است؟"},
        ],
        "adjustments": [
            _adj("like_new", "در حد نو / آکبند", 0.0,
                 ["آکبند", "در حد نو", "بدون خط", "پلمپ", "باز نشده"]),
            _adj("scratches", "خط و خش معمولی", -3.0,
                 ["خط و خش", "خط‌وخش", "خط خوردگی"]),
            _adj("cracked", "ترک / شیشه شکسته", -10.0,
                 ["ترک", "شیشه شکسته", "ال سی دی شکسته", "ال‌سی‌دی شکسته",
                  "تاچ خراب", "صفحه شکسته"]),
            _adj("no_box", "بدون کارتن / همتا", -5.0,
                 ["بدون کارتن", "بی کارتن", "همتا ندارد", "رجیستر نیست"]),
            _adj("battery_weak", "باتری ضعیف", -4.0,
                 ["باتری ضعیف", "باتری خراب", "سلامت باتری"]),
            _adj("water", "آب‌خوردگی", -12.0,
                 ["آب خورده", "آبخورده", "آب خوردگی"]),
            _adj("board", "تعمیر برد", -15.0,
                 ["تعمیر برد", "برد تعمیری", "آی سی"]),
        ],
    })
    return d


def _laptop() -> Dict[str, Any]:
    d = dict(_SOFT)
    d.update({
        "family": "laptop",
        "hunter": True,
        "dealer_mode": False,
        "slots": [
            {"key": "ram", "label": "رم", "kind": "text", "ask": True,
             "critical": False, "question": "رم چند گیگ است؟"},
            {"key": "storage", "label": "حافظه SSD/HDD", "kind": "text",
             "ask": True, "critical": False,
             "question": "SSD است یا HDD؟ ظرفیت؟"},
            {"key": "opened", "label": "باز شده / آکبند", "kind": "enum",
             "ask": True, "critical": False,
             "question": "آکبند و بازنشده است یا کارکرده؟"},
        ],
        "adjustments": [
            _adj("unopened", "آکبند / باز نشده", 0.0,
                 ["آکبند", "باز نشده", "پلمپ", "در حد نو"]),
            _adj("hdd", "هارد HDD به‌جای SSD", -6.0,
                 ["هارد", "hdd", "مکانیکی"]),
            _adj("ssd", "SSD", 0.0, ["اس اس دی", "ssd", "nvme"]),
            _adj("no_charger", "بدون شارژر", -3.0,
                 ["بدون شارژر", "آداپتور ندارد"]),
            _adj("screen", "لکه / خط روی صفحه", -8.0,
                 ["لکه صفحه", "خط صفحه", "بک‌لایت", "پیکسل سوخته"]),
            _adj("battery_weak", "باتری ضعیف", -4.0,
                 ["باتری ضعیف", "شارژ نگه نمیداره"]),
        ],
    })
    return d


def _appliance() -> Dict[str, Any]:
    d = dict(_SOFT)
    d.update({
        "family": "appliance",
        "hunter": True,
        "slots": [
            {"key": "condition", "label": "وضعیت", "kind": "enum",
             "ask": True, "critical": False,
             "question": "نو است یا کارکرده؟ ایراد دارد؟"},
        ],
        "adjustments": [
            _adj("used", "کارکرده سالم", -3.0, ["کارکرده", "استفاده شده"]),
            _adj("no_box", "بدون کارتن", -2.0, ["بدون کارتن", "بی کارتن"]),
            _adj("repair", "تعمیری", -10.0,
                 ["تعمیری", "نیاز به تعمیر", "خراب"]),
        ],
    })
    return d


def _generic() -> Dict[str, Any]:
    d = dict(_SOFT)
    d.update({
        "family": "generic",
        "hunter": True,
        "slots": [
            {"key": "condition", "label": "وضعیت کالا", "kind": "enum",
             "ask": True, "critical": False,
             "question": "نو / در حد نو / کارکرده / معیوب؟"},
        ],
        "adjustments": [
            _adj("used", "کارکرده", -3.0, ["کارکرده", "دست دوم"]),
            _adj("defect_soft", "ایراد جزئی", -8.0,
                 ["خط و خش", "لکه", "تعمیر جزئی"]),
            _adj("unopened", "باز نشده", 0.0, ["آکبند", "پلمپ", "باز نشده"]),
        ],
    })
    return d


def _estate() -> Dict[str, Any]:
    return {
        "family": "real_estate",
        "hunter": False,
        "reason": "املاک در شکارچی پشتیبانی نمی‌شود — خیلی پیچیده است",
        "slots": [],
        "adjustments": [],
        **_SOFT,
    }


_FAMILY = {
    "vehicle": _vehicle,
    "phone": _phone,
    "laptop": _laptop,
    "appliance": _appliance,
    "generic": _generic,
    "real_estate": _estate,
}

# دسته → خانواده
_SLUG_FAMILY = {
    "light": "vehicle", "vehicles": "vehicle", "motorcycles": "vehicle",
    "truck": "vehicle", "classic-car": "vehicle", "rental-car": "vehicle",
    "heavy-vehicles": "vehicle", "boat": "vehicle",
    "auto-parts-accessories": "generic",
    "mobile-phones": "phone", "mobile-tablet": "phone", "tablet": "phone",
    "mobile-tablet-accessories": "generic",
    "apple": "phone", "samsung": "phone", "xiaomi": "phone",
    "huawei": "phone", "nokia": "phone", "honor": "phone",
    "motorola": "phone", "google-pixel": "phone", "oneplus": "phone",
    "nothing": "phone", "sony": "phone", "lg": "phone",
    "oppo": "phone", "vivo": "phone", "realme": "phone",
    "laptops": "laptop", "computers": "laptop",
    "desktop-computers": "laptop",
    "computer-and-laptop-accessories": "generic",
    "asus-laptop": "laptop", "lenovo-laptop": "laptop",
    "hp-laptop": "laptop", "dell-laptop": "laptop",
    "macbook": "laptop", "acer-laptop": "laptop", "msi-laptop": "laptop",
    "game-consoles-and-video-games": "generic",
    "audio-video": "generic", "camera-camcoders": "generic",
    "telephone": "generic",
    "refrigerator-freezer": "appliance", "washers": "appliance",
    "heating-cooling": "appliance", "cookware": "generic",
    "furniture-wood": "generic", "lighting": "generic",
    "carpet": "generic", "curtains-tablecloths": "generic",
    "bathroom-accessories": "generic", "decorative": "generic",
    "home-kitchen": "generic",
    "clothing-and-shoes": "generic", "bags-shoes": "generic",
    "jewelry": "generic", "health-beauty": "generic",
    "child-baby": "generic", "personal": "generic",
    "bicycle": "generic", "sport": "generic",
    "musical-instruments": "generic", "book-student": "generic",
    "ticket": "generic", "tour-travel": "generic",
    "entertainment": "generic",
    "tools-materials-equipment": "generic",
    "industrial-machinery": "generic", "building-equipment": "generic",
    "animals": "generic", "cats": "generic", "dogs": "generic",
    "birds": "generic", "fish": "generic",
    "services": "generic", "jobs": "generic",
    "social-services": "generic",
    "real-estate": "real_estate", "apartment-sell": "real_estate",
    "apartment-rent": "real_estate", "house-villa-sell": "real_estate",
    "house-villa-rent": "real_estate", "office-sell": "real_estate",
    "office-rent": "real_estate", "shop-sell": "real_estate",
    "shop-rent": "real_estate", "plot-old": "real_estate",
    "rent-temporary": "real_estate",
    "industry-agriculture-business-sell": "real_estate",
    "industry-agriculture-business-rent": "real_estate",
}

# کلمه → دسته (خاص‌تر اول)
_KEYWORD_HINTS = (
    ("apple", ("آیفون", "iphone", "اپل")),
    ("samsung", ("سامسونگ", "samsung", "گلکسی")),
    ("xiaomi", ("شیائومی", "xiaomi", "redmi", "poco", "ردمی")),
    ("macbook", ("مک بوک", "مک‌بوک", "macbook")),
    ("laptops", ("لپ تاپ", "لپ‌تاپ", "لپتاپ", "laptop", "نوت بوک")),
    ("light", ("پراید", "پژو", "سمند", "دنا", "شاهین", "تیبا", "کوییک",
               "پارس", "رانا", "تارا", "۲۰۶", "206", "۴۰۵", "پژو پارس",
               "هیوندای", "تویوتا", "کیا", "ام وی ام")),
    ("motorcycles", ("موتور", "هوندا", "ویو", "کبیر")),
    ("washers", ("لباسشویی",)),
    ("refrigerator-freezer", ("یخچال", "فریزر")),
    ("bicycle", ("دوچرخه",)),
    ("mobile-phones", ("گوشی", "موبایل", "تلفن همراه")),
)


def guess_category(keyword: str = "", category: str = "") -> str:
    """دسته شکار از انتخاب پنل یا از روی کلمه."""
    from .categories import normalize_slug, is_real_estate
    cat = normalize_slug(category)
    if cat and is_real_estate(cat):
        return cat
    if cat:
        return cat
    n = normalize(keyword or "")
    if not n:
        return ""
    for slug, words in _KEYWORD_HINTS:
        if any(normalize(w) in n for w in words):
            return slug
    return ""


def family_of(slug: str) -> str:
    if not slug:
        return "generic"
    if slug in _SLUG_FAMILY:
        return _SLUG_FAMILY[slug]
    if slug.startswith("mobile-") or slug in ("apple", "samsung"):
        return "phone"
    return "generic"


def default_profile(category: str = "", keyword: str = "") -> Dict[str, Any]:
    slug = guess_category(keyword, category)
    fam = family_of(slug) if slug else (
        family_of(guess_category(keyword, "")) or "generic")
    if not slug and not keyword:
        fam = "generic"
    if slug and family_of(slug) == "real_estate":
        fam = "real_estate"
    factory = _FAMILY.get(fam) or _generic
    prof = copy.deepcopy(factory())
    prof["category"] = slug
    prof["keyword"] = keyword or ""
    return prof


def merge_overrides(profile: Dict[str, Any],
                    overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """درصدها و آستانه‌های کاربر روی پیش‌فرض."""
    out = copy.deepcopy(profile or default_profile())
    if not overrides or not isinstance(overrides, dict):
        return out
    for k in ("good_pct", "great_pct", "suspicious_pct", "dealer_mode",
              "km_per_year"):
        if k in overrides and overrides[k] not in (None, ""):
            if k == "dealer_mode":
                out[k] = bool(overrides[k])
            else:
                try:
                    out[k] = float(overrides[k])
                except (TypeError, ValueError):
                    pass
    user_adj = overrides.get("adjustments") or {}
    if isinstance(user_adj, dict):
        by = {a["key"]: a for a in out.get("adjustments") or []}
        for key, pct in user_adj.items():
            if key in by:
                try:
                    by[key]["pct"] = float(pct)
                except (TypeError, ValueError):
                    pass
        out["adjustments"] = list(by.values())
    elif isinstance(user_adj, list):
        by = {a["key"]: a for a in out.get("adjustments") or []}
        for item in user_adj:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "")
            if key in by and "pct" in item:
                try:
                    by[key]["pct"] = float(item["pct"])
                except (TypeError, ValueError):
                    pass
        out["adjustments"] = list(by.values())
    return out


def public_for_ui(profile: Dict[str, Any]) -> Dict[str, Any]:
    """برای پاپ‌آپ تنظیمات پیشرفته."""
    return {
        "category": profile.get("category") or "",
        "family": profile.get("family") or "generic",
        "hunter": bool(profile.get("hunter", True)),
        "reason": profile.get("reason") or "",
        "good_pct": float(profile.get("good_pct") or 8),
        "great_pct": float(profile.get("great_pct") or 15),
        "suspicious_pct": float(profile.get("suspicious_pct") or 55),
        "dealer_mode": bool(profile.get("dealer_mode")),
        "slots": list(profile.get("slots") or []),
        "adjustments": [
            {"key": a["key"], "label": a["label"], "pct": a["pct"],
             "ask": bool(a.get("ask")), "question": a.get("question") or ""}
            for a in (profile.get("adjustments") or [])
        ],
        "hint": ("پیش‌فرض‌ها نرم‌اند تا چند شکار پیدا شود. "
                 "اگر کاسب حرفه‌ای هستید درصد افت را کمی بیشتر کنید."),
    }


def extract_flags(text: str, profile: Dict[str, Any]) -> Dict[str, bool]:
    n = normalize(text or "")
    found: Dict[str, bool] = {}
    for a in profile.get("adjustments") or []:
        words = a.get("words") or []
        found[a["key"]] = any(normalize(w) in n for w in words if w)
    return found


def adjustment_pct(flags: Dict[str, bool], profile: Dict[str, Any]) -> float:
    """جمع افت (منفی). سقف −۳۵٪ تا سخت‌گیر نباشد."""
    total = 0.0
    for a in profile.get("adjustments") or []:
        if flags.get(a["key"]):
            total += float(a.get("pct") or 0)
    return max(-35.0, min(5.0, total))


def missing_ask_slots(text: str, profile: Dict[str, Any],
                      extra: Optional[Dict[str, Any]] = None) -> List[str]:
    """اسلات‌هایی که برای سؤال لازم‌اند و در متن نیستند.

    critical پیش‌فرض False است تا دمو گیر نکند؛ فقط اگر ask=True
    و هیچ نشانه‌ای در متن نباشد.
    """
    extra = extra or {}
    n = normalize(text or "")
    missing: List[str] = []
    flags = extract_flags(text, profile)
    for slot in profile.get("slots") or []:
        if not slot.get("ask"):
            continue
        key = slot["key"]
        if extra.get(key) not in (None, "", 0, "0", "unknown"):
            continue
        if key == "year" and extra.get("car_year"):
            continue
        if key == "mileage_km" and extra.get("mileage_km"):
            continue
        if key == "chassis" and extra.get("chassis") in ("ok", "hit"):
            continue
        if key == "paint" and extra.get("paint") in ("clean", "repainted", "panel"):
            continue
        # اگر پرچم مرتبط خورده، نپرس
        if key in ("paint", "chassis") and any(flags.values()):
            continue
        if key == "condition" and any(flags.values()):
            continue
        # نشانه‌های خیلی کلی در متن
        if key == "year" and ("مدل" in n or "سال" in n):
            continue
        if key == "mileage_km" and ("کیلومتر" in n or "کارکرد" in n):
            continue
        missing.append(key)
        if len(missing) >= 3:
            break
    return missing


def build_questions(profile: Dict[str, Any], missing: List[str],
                    title: str = "") -> str:
    """متن سؤال برای چت/پیامک — از روی پروفایل، نه حدس آزاد مدل."""
    slots = {s["key"]: s for s in (profile.get("slots") or [])}
    adjs = {a["key"]: a for a in (profile.get("adjustments") or [])}
    lines = []
    if title:
        lines.append("سلام، درباره «%s»:" % (title or "")[:60])
    else:
        lines.append("سلام، برای بررسی قیمت:")
    i = 1
    for key in missing[:4]:
        rec = slots.get(key) or adjs.get(key) or {}
        q = rec.get("question") or rec.get("label") or key
        lines.append("%d) %s" % (i, q))
        i += 1
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def inquiry_prompt(profile: Dict[str, Any], missing: List[str],
                   title: str = "") -> str:
    """پرامپت مدل: فقط همین سؤال‌ها را بساز، قیمت نساز."""
    qs = build_questions(profile, missing, title)
    return (
        "تو موتور درک مارکتینگ دیوار هستی. معامله نبند. قیمت نساز.\n"
        "از روی این سؤال‌های ثابت یک پیام کوتاه فارسی برای فروشنده بنویس.\n"
        "سؤال‌ها را عوض نکن، فقط مودبانه پشت هم بگذار.\n"
        "متن:\n" + (qs or "سلام، قیمت نقد نهایی چقدر است؟ سالم است؟")
    )


def fill_from_reply(text: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    """اسلات از پاسخ فروشنده — قاعده."""
    from .vehicle import extract_mileage, extract_year, inspect_vehicle
    from .pricing import parse_toman

    flags = extract_flags(text, profile)
    out: Dict[str, Any] = {"flags": flags, "adj_pct": adjustment_pct(flags, profile)}
    n = normalize(text or "")
    fam = profile.get("family")
    if fam == "vehicle":
        veh = inspect_vehicle(text)
        out["year"] = veh.get("year") or extract_year(text)
        out["mileage_km"] = veh.get("mileage_km") or extract_mileage(text)
        out["chassis"] = veh.get("chassis")
        out["paint"] = veh.get("paint")
    price = parse_toman(text)
    if price and price >= 10_000:
        out["price_toman"] = price
    if any(w in n for w in ("سالمه", "شاسی سالم", "بی رنگ", "بیرنگ")):
        out.setdefault("chassis", "ok")
    return out
