# -*- coding: utf-8 -*-
"""market_research — تحقیق بازار ایران برای شکارچی

هدف: وقتی کاربر میگه "آیفون 13 14 15 میخوام شکار کنم"، سیستم باید:
- بدونه هر مدل چه واریانت‌هایی داره (عادی/پرو/پرومکس/مینی/پلاس/نات‌اکتیو)
- چه عواملی روی قیمتش تاثیر داره (باتری، رجیستر، خط و خش، تعمیر، کارکرد...)
- درصد افت هر عامل چقدره (بر اساس تحقیق بازار 1403 ایران)
- قیمت نو/کارکرده سالم چقدره (از ترب/اینترنت)

این ماژول دانش بازار ایران را نگه می‌دارد و به تیرا می‌دهد تا هوشمند بپرسد.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import re

# دانش پایه آیفون — واریانت‌ها
IPHONE_VARIANTS = {
    "13": ["آیفون 13", "آیفون 13 مینی", "آیفون 13 پرو", "آیفون 13 پرو مکس"],
    "14": ["آیفون 14", "آیفون 14 پلاس", "آیفون 14 پرو", "آیفون 14 پرو مکس"],
    "15": ["آیفون 15", "آیفون 15 پلاس", "آیفون 15 پرو", "آیفون 15 پرو مکس"],
    "12": ["آیفون 12", "آیفون 12 مینی", "آیفون 12 پرو", "آیفون 12 پرو مکس"],
    "11": ["آیفون 11", "آیفون 11 پرو", "آیفون 11 پرو مکس"],
    "X": ["آیفون X", "آیفون XS", "آیفون XS مکس", "آیفون XR"],
}

# عوامل تاثیرگذار بر قیمت در بازار ایران 1403
PRICE_FACTORS_IPHONE = [
    {"key": "battery_low", "label": "باتری زیر 80٪", "pct": -11, "words": ["باتری 78", "باتری 75", "باتری پایین", "باتری ضعیف"], "question": "باتری چند درصده؟", "research": "باتری زیر 80٪ در بازار ایران 10-12٪ افت دارد چون تعویض باتری هزینه دارد"},
    {"key": "battery_80_85", "label": "باتری 80-85٪", "pct": -5, "words": ["باتری 80", "باتری 82", "باتری 85"], "question": "باتری دقیقاً چنده؟", "research": "باتری 80-85٪ افت 4-6٪"},
    {"key": "not_registered", "label": "بدون رجیستر / آنتن نمی‌ده", "pct": -16, "words": ["بدون رجیستر", "رجیستر نشده", "آنتن نمیده", "قفل"], "question": "رجیستر شده؟", "research": "بدون رجیستر در ایران 15-18٪ افت چون هزینه رجیستری و ریسک"},
    {"key": "scratch", "label": "خط و خش بدنه", "pct": -7, "words": ["خط و خش", "خش داره", "بدنه خش"], "question": "بدنه خط و خش داره؟", "research": "خش بدنه 5-8٪ افت"},
    {"key": "screen_scratch", "label": "خش صفحه / گلس شکسته", "pct": -9, "words": ["گلس شکسته", "صفحه خش", "ال سی دی خش"], "question": "صفحه خش یا گلس شکسته داره؟", "research": "گلس شکسته 8-10٪ افت"},
    {"key": "repaired", "label": "تعمیر شده / تعویض قطعه", "pct": -14, "words": ["تعمیر شده", "تعویض", "باز شده", "ال سی دی تعویض"], "question": "تعمیر یا تعویض شده؟", "research": "تعمیر 12-16٪ افت"},
    {"key": "faceid_off", "label": "فیس آیدی خاموش", "pct": -12, "words": ["فیس آیدی", "face id"], "question": "فیس آیدی سالمه؟", "research": "فیس آیدی خراب 10-14٪ افت"},
    {"key": "not_active", "label": "نات‌اکتیو / پلمپ", "pct": +8, "words": ["نات اکتیو", "not active", "پلمپ", "آکبند"], "question": "نات‌اکتیو یا کارکرده؟", "research": "نات‌اکتیو 6-10٪ گران‌تر از کارکرده سالم"},
    {"key": "with_box", "label": "با کارتن و لوازم", "pct": +3, "words": ["با کارتن", "لوازم کامل", "کارتن"], "question": "کارتن و لوازم داره؟", "research": "با کارتن 2-4٪ گران‌تر"},
    {"key": "low_storage", "label": "حافظه پایین (64/128)", "pct": -4, "words": ["64 گیگ", "128 گیگ"], "question": "حافظه چقدره؟", "research": "حافظه پایین نسبت به 256 افت 3-5٪"},
]

PRICE_FACTORS_CAR = [
    {"key": "paint_one", "label": "یک لکه رنگ", "pct": -6, "words": ["یک لکه", "یک تکه رنگ"], "question": "رنگ شدگی داره؟", "research": "یک لکه رنگ 5-7٪ افت"},
    {"key": "paint_two", "label": "دو لکه رنگ", "pct": -10, "words": ["دو لکه", "دو تکه"], "question": "چند لکه رنگ؟", "research": "دو لکه 9-11٪"},
    {"key": "around_paint", "label": "دور رنگ", "pct": -14, "words": ["دور رنگ", "تمام رنگ"], "question": "دور رنگه یا کامل رنگ؟", "research": "دور رنگ 12-16٪ افت"},
    {"key": "chassis_hit", "label": "ضربه شاسی / شاسی خورده", "pct": -22, "words": ["شاسی", "ضربه", "سینی"], "question": "شاسی ضربه داره؟", "research": "شاسی 20-25٪ افت"},
]

def get_iphone_variants(series: str) -> List[str]:
    """برای سری 13، واریانت‌های کامل برگردان."""
    s = str(series).strip()
    if s in IPHONE_VARIANTS:
        return IPHONE_VARIANTS[s]
    # اگر عدد مثل 13 پرو مکس داده، همون را برگردان
    return [f"آیفون {s}"]

def get_all_iphone_series_from_text(text: str) -> List[str]:
    """از متن کاربر سری‌های آیفون را استخراج کن: 13 14 15"""
    nums = re.findall(r"(?:iphone|آیفون)?\s*(1[0-5]|X[SR]?)\b", text, re.I)
    # یکتا
    seen = []
    for n in nums:
        n_clean = n.strip().upper() if n.upper().startswith("X") else n.strip()
        if n_clean not in seen:
            seen.append(n_clean)
    return seen

def get_price_factors_for_category(category: str) -> List[Dict[str, Any]]:
    cat = (category or "").lower()
    if "mobile" in cat or "phone" in cat or "iphone" in cat or "apple" in cat:
        return PRICE_FACTORS_IPHONE
    if "light" in cat or "car" in cat or "vehicle" in cat:
        return PRICE_FACTORS_CAR
    return PRICE_FACTORS_IPHONE  # پیش‌فرض موبایل

def research_product(product_keyword: str) -> Dict[str, Any]:
    """تحقیق بازار برای یک محصول — واریانت‌ها + عوامل + توضیح"""
    kw = (product_keyword or "").lower()
    # تشخیص آیفون
    if "آیفون" in product_keyword or "iphone" in kw:
        series_list = get_all_iphone_series_from_text(product_keyword)
        if not series_list:
            # اگر فقط آیفون 13 گفته، 13 را بگیر
            m = re.search(r"(1[0-5])", product_keyword)
            if m:
                series_list = [m.group(1)]
            else:
                series_list = ["13", "14", "15"]
        variants = []
        for s in series_list:
            variants.extend(get_iphone_variants(s))
        # یکتا
        uniq_variants = []
        for v in variants:
            if v not in uniq_variants:
                uniq_variants.append(v)
        # عوامل
        factors = PRICE_FACTORS_IPHONE
        # توضیح بازار ایران
        market_note = (
            "بازار ایران 1403: آیفون نات‌اکتیو 6-10٪ گران‌تر از کارکرده سالم، "
            "بدون رجیستر 15-18٪ ارزان‌تر، باتری زیر 80٪ 10-12٪ افت، تعمیر 12-16٪ افت، "
            "خط و خش 5-8٪ افت. قیمت نو از ترب گرفته می‌شود، دست دوم سالم معمولاً 15-25٪ زیر نو."
        )
        return {
            "product": product_keyword,
            "type": "iphone",
            "series": series_list,
            "variants": uniq_variants,
            "factors": factors,
            "market_note": market_note,
            "has_variants": True,
        }
    # سایر کالاها
    return {
        "product": product_keyword,
        "type": "generic",
        "series": [],
        "variants": [product_keyword],
        "factors": get_price_factors_for_category(""),
        "market_note": "قیمت بر اساس میانه آگهی‌های همان دسته + افت وضعیت محاسبه می‌شود.",
        "has_variants": False,
    }

def build_hunter_adv_from_research(research: Dict[str, Any], sell_price: int, profit_pct: float) -> Dict[str, Any]:
    """از تحقیق، تنظیمات پیشرفته شکارچی بساز."""
    factors = research.get("factors", [])
    adjustments = {}
    for f in factors:
        adjustments[f["key"]] = f["pct"]
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
