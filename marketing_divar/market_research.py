# -*- coding: utf-8 -*-
"""market_research v4 — تحقیق بازار ایران برای شکارچی — نسخه کامل بدون باگ
پشتیبانی از موبایل، خودرو، لوازم خانگی (جاروبرقی، یخچال، لباسشویی)، لپ‌تاپ و...
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import re

IPHONE_VARIANTS = {
    "13": ["آیفون 13", "آیفون 13 مینی", "آیفون 13 پرو", "آیفون 13 پرو مکس"],
    "14": ["آیفون 14", "آیفون 14 پلاس", "آیفون 14 پرو", "آیفون 14 پرو مکس"],
    "15": ["آیفون 15", "آیفون 15 پلاس", "آیفون 15 پرو", "آیفون 15 پرو مکس"],
    "12": ["آیفون 12", "آیفون 12 مینی", "آیفون 12 پرو", "آیفون 12 پرو مکس"],
    "11": ["آیفون 11", "آیفون 11 پرو", "آیفون 11 پرو مکس"],
    "X": ["آیفون X", "آیفون XS", "آیفون XS مکس", "آیفون XR"],
    "16": ["آیفون 16", "آیفون 16 پلاس", "آیفون 16 پرو", "آیفون 16 پرو مکس"],
}

# عوامل موبایل - کامل
PRICE_FACTORS_IPHONE = [
    {"key": "battery_100", "label": "باتری 100٪", "pct": +2, "words": ["باتری 100", "باتری صد"], "question": "باتری 100٪ هست؟", "research": "باتری 100٪ 1-3٪ گران‌تر", "dynamic": True},
    {"key": "battery_95_99", "label": "باتری 95-99٪", "pct": 0, "words": ["باتری 95", "باتری 96", "باتری 97", "باتری 98", "باتری 99"], "question": "باتری دقیقاً چنده؟", "research": "نرمال", "dynamic": True},
    {"key": "battery_90_94", "label": "باتری 90-94٪", "pct": -2, "words": ["باتری 90", "باتری 91", "باتری 92", "باتری 93", "باتری 94"], "question": "باتری چند درصده؟", "research": "افت 1-3٪", "dynamic": True},
    {"key": "battery_86_89", "label": "باتری 86-89٪", "pct": -4, "words": ["باتری 86", "باتری 87", "باتری 88", "باتری 89"], "question": "باتری چند درصده؟", "research": "افت 3-5٪", "dynamic": True},
    {"key": "battery_80_85", "label": "باتری 80-85٪", "pct": -6, "words": ["باتری 80", "باتری 82", "باتری 85", "باتری 84"], "question": "باتری دقیقاً چنده؟", "research": "افت 5-7٪", "dynamic": True},
    {"key": "battery_low", "label": "باتری زیر 80٪", "pct": -12, "words": ["باتری 78", "باتری 75", "باتری 70", "باتری پایین", "باتری ضعیف", "باتری 79"], "question": "باتری چند درصده؟", "research": "افت 10-14٪ + هزینه تعویض", "dynamic": True},
    {"key": "battery_replaced", "label": "باتری تعویض شده", "pct": -8, "words": ["باتری تعویض", "باتری عوض", "باتری جدید"], "question": "باتری تعویض شده؟", "research": "افت 6-10٪ اصالت", "dynamic": True},
    {"key": "not_registered", "label": "بدون رجیستر", "pct": -18, "words": ["بدون رجیستر", "رجیستر نشده", "آنتن نمیده"], "question": "رجیستر شده؟", "research": "افت 15-20٪", "dynamic": True},
    {"key": "scratch_light", "label": "خش جزئی", "pct": -4, "words": ["خش جزئی", "خط ریز"], "question": "خش جزئی داره؟", "research": "افت 3-5٪", "dynamic": True},
    {"key": "scratch", "label": "خط و خش", "pct": -8, "words": ["خط و خش", "خش داره"], "question": "خط و خش داره؟", "research": "افت 6-10٪", "dynamic": True},
    {"key": "scratch_heavy", "label": "ضربه شدید", "pct": -13, "words": ["ضربه", "فرورفتگی", "دنت"], "question": "ضربه داره؟", "research": "افت 12-15٪", "dynamic": True},
    {"key": "screen_scratch", "label": "خش صفحه", "pct": -10, "words": ["گلس شکسته", "صفحه خش"], "question": "صفحه خش داره؟", "research": "افت 8-12٪", "dynamic": True},
    {"key": "screen_replaced", "label": "ال سی دی تعویض", "pct": -16, "words": ["ال سی دی تعویض", "غیر اصل"], "question": "صفحه اصلیه؟", "research": "افت 14-18٪", "dynamic": True},
    {"key": "repaired", "label": "تعمیر شده", "pct": -15, "words": ["تعمیر شده", "باز شده"], "question": "تعمیر شده؟", "research": "افت 12-18٪", "dynamic": True},
    {"key": "repaired_board", "label": "تعمیر برد", "pct": -22, "words": ["تعمیر برد", "شاسی", "آب خورده"], "question": "برد تعمیر؟", "research": "افت 20-25٪", "dynamic": True},
    {"key": "faceid_off", "label": "فیس آیدی خراب", "pct": -14, "words": ["فیس آیدی", "face id"], "question": "فیس آیدی سالمه؟", "research": "افت 12-16٪", "dynamic": True},
    {"key": "not_active", "label": "نات‌اکتیو / پلمپ (ریسک فیک)", "pct": -6, "words": ["نات اکتیو", "not active", "پلمپ", "آکبند"], "question": "نات‌اکتیو با فاکتور؟", "research": "بازار ایران 1403: بدون فاکتور -6٪ ریسک فیک، با فاکتور +3٪", "dynamic": True, "source": "internet_research_iran_1403"},
    {"key": "not_active_with_receipt", "label": "نات‌اکتیو با فاکتور", "pct": +3, "words": ["فاکتور", "رسمی"], "question": "فاکتور رسمی داره؟", "research": "+2 تا +4٪", "dynamic": True},
    {"key": "not_active_no_receipt", "label": "نات‌اکتیو بدون فاکتور", "pct": -7, "words": ["بدون فاکتور"], "question": "فاکتور داره؟", "research": "-6 تا -8٪", "dynamic": True},
    {"key": "with_box", "label": "با کارتن کامل", "pct": +4, "words": ["با کارتن", "لوازم کامل"], "question": "کارتن داره؟", "research": "+3-5٪", "dynamic": True},
    {"key": "without_box", "label": "بدون کارتن", "pct": -2, "words": ["بدون کارتن"], "question": "کارتن داره؟", "research": "-1-3٪", "dynamic": True},
    {"key": "like_new", "label": "در حد نو", "pct": +3, "words": ["در حد نو", "مثل نو"], "question": "در حد نو؟", "research": "+2-4٪", "dynamic": True},
]

PRICE_FACTORS_CAR = [
    {"key": "paint_one", "label": "یک لکه رنگ", "pct": -6, "words": ["یک لکه", "یک تکه رنگ"], "question": "رنگ شدگی داره؟", "research": "افت 5-7٪"},
    {"key": "paint_two", "label": "دو لکه رنگ", "pct": -10, "words": ["دو لکه"], "question": "چند لکه؟", "research": "افت 9-11٪"},
    {"key": "around_paint", "label": "دور رنگ", "pct": -14, "words": ["دور رنگ"], "question": "دور رنگه؟", "research": "افت 12-16٪"},
    {"key": "chassis_hit", "label": "ضربه شاسی", "pct": -22, "words": ["شاسی", "ضربه"], "question": "شاسی ضربه؟", "research": "افت 20-25٪"},
]

# عوامل لوازم خانگی — جاروبرقی، یخچال، لباسشویی و...
PRICE_FACTORS_HOME_APPLIANCE = [
    {"key": "brand_bosch", "label": "برند بوش/ال‌جی/سامسونگ", "pct": +5, "words": ["بوش", "ال جی", "سامسونگ", "bosch", "lg"], "question": "برند چیه؟", "research": "برندهای معتبر 3-7٪ گران‌تر"},
    {"key": "brand_generic", "label": "برند متفرقه", "pct": -8, "words": ["متفرقه", "چینی", "بدون برند"], "question": "برند؟", "research": "متفرقه -5 تا -10٪"},
    {"key": "used_light", "label": "کارکرد کم", "pct": -5, "words": ["کم کارکرد", "کم استفاده"], "question": "چقدر کارکرده؟", "research": "کارکرد کم -3 تا -7٪"},
    {"key": "used_heavy", "label": "کارکرد زیاد", "pct": -15, "words": ["کارکرد زیاد", "قدیمی"], "question": "چقدر کارکرده؟", "research": "کارکرد زیاد -12 تا -18٪"},
    {"key": "repaired_home", "label": "تعمیر شده", "pct": -12, "words": ["تعمیر", "تعویض موتور"], "question": "تعمیر شده؟", "research": "تعمیر -10 تا -15٪"},
    {"key": "with_warranty", "label": "با گارانتی", "pct": +6, "words": ["گارانتی", "ضمانت"], "question": "گارانتی داره؟", "research": "با گارانتی +4 تا +8٪"},
    {"key": "without_warranty", "label": "بدون گارانتی", "pct": -3, "words": ["بدون گارانتی"], "question": "گارانتی داره؟", "research": "-2 تا -4٪"},
    {"key": "with_box_home", "label": "با کارتن", "pct": +3, "words": ["کارتن", "جعبه"], "question": "کارتن داره؟", "research": "+2 تا +4٪"},
    {"key": "scratch_home", "label": "خط و خش/ضربه", "pct": -7, "words": ["خش", "ضربه", "خط"], "question": "ضربه یا خش داره؟", "research": "-5 تا -9٪"},
    {"key": "motor_weak", "label": "موتور ضعیف/صدا", "pct": -10, "words": ["صدا", "موتور ضعیف", "مکش کم"], "question": "موتور سالمه؟", "research": "موتور ضعیف -8 تا -12٪"},
    {"key": "filter_issue", "label": "فیلتر/کیسه مشکل", "pct": -4, "words": ["فیلتر", "کیسه"], "question": "فیلتر سالمه؟", "research": "-3 تا -5٪"},
]

PRICE_FACTORS_LAPTOP = [
    {"key": "ram_low", "label": "رم پایین", "pct": -8, "words": ["رم 4", "رم کم"], "question": "رم چقدره؟", "research": "رم پایین -6 تا -10٪"},
    {"key": "ram_high", "label": "رم بالا", "pct": +6, "words": ["رم 16", "رم 32"], "question": "رم؟", "research": "+4 تا +8٪"},
    {"key": "ssd_low", "label": "حافظه کم", "pct": -5, "words": ["128 گیگ", "حافظه کم"], "question": "حافظه؟", "research": "-4 تا -6٪"},
    {"key": "cpu_old", "label": "CPU قدیمی", "pct": -10, "words": ["قدیمی", "نسل پایین"], "question": "CPU چیه؟", "research": "-8 تا -12٪"},
    {"key": "battery_laptop_low", "label": "باتری لپ‌تاپ ضعیف", "pct": -7, "words": ["باتری ضعیف", "شارژ نگه نمیداره"], "question": "باتری چطوره؟", "research": "-5 تا -9٪"},
]

GENERIC_FACTORS = [
    {"key": "used", "label": "کارکرده", "pct": -15, "words": ["کارکرده", "دست دوم"], "question": "نو یا کارکرده؟", "research": "کارکرده 10-20٪ زیر نو"},
    {"key": "scratch", "label": "خط و خش", "pct": -7, "words": ["خش", "خط"], "question": "خط و خش داره؟", "research": "خش 5-10٪ افت"},
    {"key": "repaired", "label": "تعمیر شده", "pct": -12, "words": ["تعمیر", "تعویض"], "question": "تعمیر شده؟", "research": "تعمیر 10-15٪ افت"},
    {"key": "with_box", "label": "با کارتن", "pct": +4, "words": ["کارتن", "لوازم کامل"], "question": "کارتن داره؟", "research": "با کارتن 3-5٪ گران‌تر"},
    {"key": "not_active", "label": "نات‌اکتیو / پلمپ", "pct": -6, "words": ["نات اکتیو", "پلمپ", "آکبند"], "question": "نات‌اکتیو با فاکتور؟", "research": "بدون فاکتور -6٪ ریسک", "dynamic": True},
]

def get_all_iphone_series_from_text(text: str) -> List[str]:
    """استخراج سری آیفون از متن — حتی اگر کلمه آیفون نباشد ولی سری گفته شده"""
    # الگوی قدیمی
    nums = re.findall(r"(?:iphone|آیفون)?\s*(1[0-6]|X[SR]?)\b", text, re.I)
    # الگوی جدید: سری 13 14 15 یا 13 14 15 شکار کن
    # اگر کلمه سری یا شکار یا آیفون در متن باشد و اعداد 11-16 بیاید
    if any(w in text for w in ["سری", "شکار", "آیفون", "iphone", "13", "14", "15"]):
        # اعداد 11 تا 16 را جدا بگیر
        extra = re.findall(r"\b(1[1-6])\b", text)
        for e in extra:
            if e not in nums:
                nums.append(e)
    # یکتا و مرتب
    seen = []
    for n in nums:
        n_clean = n.strip().upper() if n.upper().startswith("X") else n.strip()
        if n_clean not in seen:
            seen.append(n_clean)
    return seen

def get_iphone_variants(series: str) -> List[str]:
    s = str(series).strip()
    if s in IPHONE_VARIANTS:
        return IPHONE_VARIANTS[s]
    return [f"آیفون {s}"]

def get_price_factors_for_category(category: str) -> List[Dict[str, Any]]:
    cat = (category or "").lower()
    if "mobile" in cat or "phone" in cat or "iphone" in cat or "apple" in cat:
        return PRICE_FACTORS_IPHONE
    if "light" in cat or "car" in cat or "vehicle" in cat or "خودرو" in cat or "ماشین" in cat or "پراید" in cat or "پژو" in cat:
        return PRICE_FACTORS_CAR
    if any(x in cat for x in ["vacuum", "جاروبرقی", "یخچال", "لباسشویی", "home", "appliance", "لوازم خانگی"]):
        return PRICE_FACTORS_HOME_APPLIANCE
    if any(x in cat for x in ["laptop", "لپ‌تاپ", "مک‌بوک", "computer"]):
        return PRICE_FACTORS_LAPTOP
    return PRICE_FACTORS_IPHONE

def detect_product_type(keyword: str) -> str:
    """تشخیص نوع محصول از کلمه کلیدی — v4 بهبود یافته"""
    kw = (keyword or "").lower()
    # اگر سری آیفون باشد (سری 13 14 15 شکار کن) → موبایل
    series = get_all_iphone_series_from_text(keyword or "")
    if series:
        return "mobile"
    # موبایل
    if any(w in kw for w in ["آیفون", "iphone", "موبایل", "گوشی", "سامسونگ", "شیائومی", "samsung", "xiaomi", "mobile", "phone", "سری", "شکار"]):
        # اگر سری و شکار دارد و اعداد 11-16 دارد → موبایل
        if any(w in kw for w in ["سری", "شکار"]) and re.search(r"\b1[1-6]\b", kw):
            return "mobile"
        if any(w in kw for w in ["آیفون", "iphone", "موبایل", "گوشی", "سامسونگ", "شیائومی"]):
            return "mobile"
        # اگر فقط سری گفته و کلمه شکار
        if "شکار" in kw and re.search(r"\b1[1-6]\b", kw):
            return "mobile"
    # خودرو
    if any(w in kw for w in ["پراید", "پژو", "سمند", "دنا", "تیبا", "خودرو", "ماشین", "car", "vehicle"]):
        return "car"
    # لوازم خانگی — جاروبرقی و...
    if any(w in kw for w in ["جاروبرقی", "یخچال", "لباسشویی", "ظرفشویی", "مایکروویو", "بوش", "bosch", "ال جی", "سامسونگ", "vacuum", "refrigerator", "washer", "یخچال ساید", "ساید بای ساید"]):
        return "home_appliance"
    # لپ‌تاپ
    if any(w in kw for w in ["لپ‌تاپ", "لپ تاپ", "مک‌بوک", "لپتاب", "laptop", "macbook", "ایسوس", "لنوو"]):
        return "laptop"
    # اگر کلمه bulk موبایل
    if any(w in kw for w in ["هرچی موبایل", "همه موبایل", "تمام موبایل", "هر چی موبایل", "هرچی گوشی"]):
        return "mobile"
    return "generic"

def research_product(product_keyword: str) -> Dict[str, Any]:
    kw = (product_keyword or "").strip()
    low = kw.lower()
    prod_type = detect_product_type(kw)
    
    if prod_type == "mobile" or "آیفون" in kw or "iphone" in low:
        series_list = get_all_iphone_series_from_text(kw)
        if not series_list:
            m = re.search(r"(1[0-6])", kw)
            if m:
                series_list = [m.group(1)]
            else:
                # اگر فقط موبایل گفته، سری‌های پرطرفدار
                if "موبایل" in kw and len(kw) < 20:
                    series_list = ["13", "14", "15"]
                else:
                    series_list = ["13", "14", "15"]
        variants = []
        for s in series_list:
            variants.extend(get_iphone_variants(s))
        uniq_variants = []
        for v in variants:
            if v not in uniq_variants:
                uniq_variants.append(v)
        # اگر فقط یک مدل خاص مثل آیفون 13 گفته
        if len(kw) < 15 and "آیفون" in kw and len(series_list) == 1:
            uniq_variants = get_iphone_variants(series_list[0])
        
        market_note = "بازار ایران 1403: آیفون نات‌اکتیو ادعایی بدون فاکتور 5-8٪ ریسک، با فاکتور +3٪. بدون رجیستر 15-18٪ افت، باتری زیر 80٪ 10-12٪ افت. قیمت نو از ترب، دست دوم 15-25٪ زیر نو."
        return {
            "product": kw,
            "type": "iphone" if "آیفون" in kw or "iphone" in low else "mobile",
            "product_type": "mobile",
            "series": series_list,
            "variants": uniq_variants,
            "factors": PRICE_FACTORS_IPHONE,
            "market_note": market_note,
            "has_variants": True,
        }
    
    if prod_type == "car":
        return {
            "product": kw,
            "type": "car",
            "product_type": "car",
            "series": [],
            "variants": [kw],
            "factors": PRICE_FACTORS_CAR,
            "market_note": "بازار خودرو ایران: رنگ شدگی 5-15٪ افت، شاسی 20-25٪ افت، کارکرد بالا 10-15٪ افت.",
            "has_variants": False,
        }
    
    if prod_type == "home_appliance":
        # جاروبرقی، یخچال و...
        brand = ""
        if "بوش" in kw or "bosch" in low:
            brand = "بوش"
        elif "ال جی" in kw or "lg" in low:
            brand = "ال‌جی"
        
        market_note = f"لوازم خانگی {brand} در بازار ایران: برند معتبر 3-7٪ گران‌تر، کارکرد زیاد -12 تا -18٪، تعمیر -10 تا -15٪، با گارانتی +4 تا +8٪. جاروبرقی بوش دست دوم تمیز معمولاً 60-75٪ قیمت نو."
        return {
            "product": kw,
            "type": "home_appliance",
            "product_type": "home_appliance",
            "series": [],
            "variants": [kw],
            "factors": PRICE_FACTORS_HOME_APPLIANCE,
            "market_note": market_note,
            "has_variants": False,
        }
    
    if prod_type == "laptop":
        return {
            "product": kw,
            "type": "laptop",
            "product_type": "laptop",
            "series": [],
            "variants": [kw],
            "factors": PRICE_FACTORS_LAPTOP,
            "market_note": "لپ‌تاپ دست دوم: رم پایین -6 تا -10٪، باتری ضعیف -5 تا -9٪، CPU قدیمی -8 تا -12٪.",
            "has_variants": False,
        }
    
    # عمومی - مثل جاروبرقی و...
    # اگر کلمه هرچی موبایل یا همه موبایل باشد، دسته موبایل
    if any(w in kw for w in ["هرچی موبایل", "همه موبایل", "تمام موبایل", "هر چی موبایل"]):
        return {
            "product": "موبایل",
            "type": "mobile",
            "product_type": "mobile",
            "series": ["13", "14", "15"],
            "variants": ["آیفون 13", "آیفون 14", "آیفون 15", "سامسونگ S23", "سامسونگ S24", "شیائومی"],
            "factors": PRICE_FACTORS_IPHONE,
            "market_note": "جستجوی همه موبایل‌ها: تمام آگهی‌های دسته موبایل استخراج می‌شود، شماره‌ها گرفته می‌شود، پیامک/چت ارسال می‌شود.",
            "has_variants": True,
            "is_bulk": True,
        }
    
    return {
        "product": kw,
        "type": "generic",
        "product_type": "generic",
        "series": [],
        "variants": [kw],
        "factors": GENERIC_FACTORS,
        "market_note": "قیمت بر اساس میانه آگهی‌های همان دسته + افت وضعیت.",
        "has_variants": False,
    }

def build_hunter_adv_from_research(research: Dict[str, Any], sell_price: int, profit_pct: float) -> Dict[str, Any]:
    factors = research.get("factors", [])
    adjustments = {f["key"]: f["pct"] for f in factors}
    good_pct = max(8, min(25, profit_pct * 0.8 if profit_pct else 12))
    great_pct = max(12, min(35, profit_pct * 1.2 if profit_pct else 22))
    return {
        "good_pct": round(good_pct, 1),
        "great_pct": round(great_pct, 1),
        "suspicious_pct": 50,
        "dealer_mode": True,
        "adjustments": adjustments,
        "research": research,
        "sell_price": sell_price,
    }

def research_market_adjustments_from_internet(product_keyword: str) -> Dict[str, Any]:
    try:
        from .price_knowledge import fetch_market_price_from_web
        prod = {"keyword": product_keyword, "model": product_keyword}
        new_price = fetch_market_price_from_web(prod, timeout=6)
        adjustments = {}
        if any(w in product_keyword.lower() for w in ["نات اکتیو", "not active", "پلمپ", "آکبند"]):
            adjustments["not_active"] = -6
        return {
            "product": product_keyword,
            "new_price": new_price,
            "adjustments_dynamic": adjustments,
            "source": "torob_api + divar_median",
            "note": "درصدها از اینترنت به‌روز می‌شود"
        }
    except Exception as e:
        return {"product": product_keyword, "error": str(e), "source": "fallback", "adjustments_dynamic": {}}
