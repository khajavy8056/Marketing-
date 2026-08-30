# -*- coding: utf-8 -*-
"""بررسی تخصصی خودرو برای شکارچی — شاسی، رنگ، مدل، کارکرد.

قیمت پایین به‌خاطر شاسی ضربه‌خورده یا دوررنگ هرگز «شکار عالی» نیست.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from .matching import normalize

_CHASSIS_OK = ("شاسی سالم", "شاسی‌سالم", "شاسی ها سالم", "شاسیها سالم",
               "شاسی هاش سالم", "دو شاسی سالم")
_CHASSIS_HIT = ("شاسی ضربه", "شاسی‌ضربه", "شاسی رنگ", "شاسی خورده",
                "شاسی چپی", "شاسی عقب رنگ", "شاسی جلو رنگ",
                "شاسی تعویض", "ستون خورده", "سینی رنگ")
_PAINT_CLEAN = ("بی رنگ", "بیرنگ", "فاقد رنگ", "بدون رنگ", "صفر رنگ",
                "رنگ نشده", "رنگ‌نخورده")
_PAINT_BAD = ("دور رنگ", "دوررنگ", "دورِ رنگ", "چند لکه رنگ",
              "گلگیر رنگ", "گلگیر تعویض", "کاپوت رنگ", "درب رنگ",
              "رنگ شده", "رنگ‌شده", "لیسه گیری", "لیسه‌گیری",
              "صافکاری رنگ", "نقاشی شده")
_ACCIDENT = ("تصادفی", "تصادف داشته", "چپی", "چپ کرده",
             "سقف رنگ", "اتاق تعویض")
_MECH = ("تعویض موتور", "موتور تعویض", "گیربکس تعویض", "تعویض گیربکس",
         "سیلندر تراش", "واشر زده", "یاتاقان")


def _has(n: str, words) -> bool:
    return any(normalize(w) in n for w in words)


def extract_year(text: str) -> Optional[int]:
    raw = normalize(text or "")
    m = re.search(r"(?:مدل|سال)\s*(1[34]\d{2})", raw)
    if m:
        y = int(m.group(1))
        if 1370 <= y <= 1410:
            return y
    m = re.search(r"\b(13[7-9]\d|140[0-9])\b", raw)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(19[89]\d|20[0-2]\d)\b", raw)
    if m:
        y = int(m.group(1))
        if 1988 <= y <= 2028:
            return y
    return None


def extract_mileage(text: str) -> Optional[int]:
    raw = normalize(text or "")
    m = re.search(
        r"(\d{1,3}(?:[.,]\d{3})+|\d{4,7})\s*(?:کیلومتر|km|ک\.م)",
        raw, re.I)
    if not m:
        m = re.search(r"کارکرد\s*(\d{1,3}(?:[.,]\d{3})+|\d{3,7})", raw)
    if not m:
        return None
    digits = re.sub(r"[^\d]", "", m.group(1))
    try:
        n = int(digits)
    except ValueError:
        return None
    if 100 <= n <= 900_000:
        return n
    return None


def inspect_vehicle(text: str) -> Dict[str, Any]:
    n = normalize(text)
    chassis = "unknown"
    if _has(n, _CHASSIS_OK):
        chassis = "ok"
    if _has(n, _CHASSIS_HIT):
        chassis = "hit"
    paint = "unknown"
    if _has(n, _PAINT_CLEAN):
        paint = "clean"
    if _has(n, _PAINT_BAD):
        paint = "repainted"
    accident = _has(n, _ACCIDENT)
    mechanical = _has(n, _MECH)
    # رنگ/شاسی شکار را نمی‌کشند — افت قیمت در پروفایل شکارچی اعمال می‌شود
    hunter_block = False
    is_defect = chassis == "hit" or accident or mechanical
    year = extract_year(text)
    km = extract_mileage(text)
    bits = []
    if chassis == "hit":
        bits.append("شاسی ضربه/رنگ")
    elif chassis == "ok":
        bits.append("شاسی سالم")
    if paint == "repainted":
        bits.append("رنگ‌شدگی/دوررنگ")
    elif paint == "clean":
        bits.append("بدون رنگ")
    if accident:
        bits.append("تصادفی")
    if mechanical:
        bits.append("ایراد مکانیکی")
    if year:
        bits.append("مدل %s" % year)
    if km:
        bits.append("کارکرد %s" % km)
    return {
        "chassis": chassis,
        "paint": paint,
        "accident": accident,
        "mechanical": mechanical,
        "year": year,
        "mileage_km": km,
        "hunter_block": hunter_block,
        "is_defect": is_defect,
        "summary_fa": "؛ ".join(bits) or "خودرو بدون نشانهٔ شاسی/رنگ در متن",
        "source": "vehicle_rules",
    }
