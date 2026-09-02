# -*- coding: utf-8 -*-
"""پروفایل شکارچی هر دسته — افت قیمت، اسلات، سؤال جای‌خالی.

بر اساس تحقیق بازار ایران (دیوار/شیپور ۱۴۰۲-۱۴۰۳):
- خودرو: رنگ، شاسی، تصادف، کارکرد، بیمه، تاکسی/صفر
- موبایل: وضعیت بدنه، باتری، رجیستری، کارتن، آب‌خوردگی، تعمیر برد
- لپ‌تاپ: SSD/HDD، رم، باتری، صفحه، آکبند
- لوازم خانگی و عمومی: کارکرده/نو، تعمیری

پیش‌فرض‌ها نرم‌اند تا دمو چند شکار پیدا کند.
کاربر در تنظیمات پیشرفته درصدها را سفت می‌کند و می‌تواند آپشن جدید اضافه کند.

هشدار اولیه: این بخش تخصصی است — یک کاسب حرفه‌ای پر کرده.
اگر بلد نیستید دست نزنید، اگر کاسبید درصدها را بر اساس تجربه خود تنظیم کنید.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional

from .matching import normalize

# آستانه‌های نرم — دمو باید چیزی پیدا کند (کاربر حرفه‌ای سفت‌تر می‌کند)
_SOFT = {"good_pct": 8.0, "great_pct": 15.0, "suspicious_pct": 55.0}

# آستانه‌های پیشنهادی کاسب حرفه‌ای (برای راهنما)
_PRO_HINT = {
    "vehicle": {"good_pct": 12.0, "great_pct": 22.0, "suspicious_pct": 45.0},
    "phone": {"good_pct": 10.0, "great_pct": 20.0, "suspicious_pct": 50.0},
    "laptop": {"good_pct": 10.0, "great_pct": 18.0, "suspicious_pct": 48.0},
    "appliance": {"good_pct": 12.0, "great_pct": 25.0, "suspicious_pct": 55.0},
    "generic": {"good_pct": 10.0, "great_pct": 20.0, "suspicious_pct": 50.0},
}


def _adj(key: str, label: str, pct: float, words: List[str],
         ask: bool = False, home_block: bool = False,
         question: str = "", research: str = "") -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "pct": float(pct),
        "words": list(words),
        "ask": ask,
        "home_block": home_block,
        "question": question or (label + "؟"),
        "research": research,  # توضیح تحقیق بازار
    }


def _vehicle() -> Dict[str, Any]:
    """خودرو — دقیق‌ترین بخش، بر اساس بازار ایران."""
    d = dict(_SOFT)
    d.update(_PRO_HINT["vehicle"])
    # برای دمو نرم‌تر برمی‌گردانیم، ولی research نگه می‌داریم
    d["good_pct"] = 10.0
    d["great_pct"] = 18.0
    d["suspicious_pct"] = 48.0
    d.update({
        "family": "vehicle",
        "hunter": True,
        "dealer_mode": False,
        "km_per_year": 20000,
        "year_depreciation_per_year": 5.0,  # هر سال افت 5% نسبت به صفر
        "research_note": "بر اساس دیوار ۱۴۰۳: پراید/پژو/دنا/شاهین — رنگ و شاسی بیشترین تاثیر",
        "warning": "بخش تخصصی — یک کاسب حرفه‌ای این درصدها را پر کرده. اگر بلد نیستید دست نزنید.",
        "slots": [
            {"key": "year", "label": "مدل / سال", "kind": "year",
             "ask": True, "critical": False,
             "question": "مدل و سال دقیق خودرو چیست؟"},
            {"key": "mileage_km", "label": "کارکرد (کیلومتر)", "kind": "int",
             "ask": True, "critical": False,
             "question": "کارکرد واقعی چند کیلومتر است؟"},
            {"key": "chassis", "label": "وضعیت شاسی", "kind": "enum",
             "ask": True, "critical": True,
             "question": "شاسی سالم است یا ضربه/رنگ دارد؟"},
            {"key": "paint", "label": "رنگ بدنه", "kind": "enum",
             "ask": True, "critical": False,
             "question": "بی‌رنگ است یا چند نقطه رنگ دارد (گلگیر/کاپوت/دوررنگ)؟"},
            {"key": "insurance", "label": "بیمه", "kind": "text",
             "ask": False, "critical": False,
             "question": "بیمه تا کی دارد؟"},
            {"key": "transmission", "label": "گیربکس", "kind": "enum",
             "ask": False, "critical": False,
             "question": "دنده‌ای یا اتومات؟"},
        ],
        "adjustments": [
            # رنگ — تحقیق: یک لکه 2.5-4%، دو لکه 6-8%، دوررنگ 12-15%، تمام رنگ 18-22%
            _adj("paint_one_small", "یک لکه رنگ کوچک (در حد مالیدگی)", -2.5,
                 ["یک لکه رنگ", "مالیدگی رنگ", "خش رنگ"],
                 question="یک لکه رنگ کوچک دارد؟",
                 research="بازار: 2.5% افت"),
            _adj("paint_panel", "یک قطعه رنگ (گلگیر/درب/کاپوت)", -4.0,
                 ["گلگیر رنگ", "درب رنگ", "کاپوت رنگ", "صندوق رنگ", "یک لکه رنگ"],
                 question="گلگیر یا کاپوت رنگ دارد؟",
                 research="بازار: 3-5% افت، اگر شاسی سالم باشد هنوز شکار محسوب می‌شود"),
            _adj("paint_two", "دو قطعه رنگ", -7.0,
                 ["دو لکه رنگ", "دو قطعه رنگ", "دو درب رنگ"],
                 research="بازار: 6-8%"),
            _adj("paint_multi", "چند قطعه رنگ (3+)", -11.0,
                 ["چند لکه رنگ", "سه نقطه رنگ", "چند جا رنگ"],
                 research="بازار: 10-12%"),
            _adj("paint_full", "دوررنگ", -14.0,
                 ["دور رنگ", "دوررنگ"],
                 research="بازار: 12-15% — حتی دوررنگ اگر قیمت خیلی پایین باشد شکار است"),
            _adj("paint_all", "تمام‌رنگ / کامل رنگ", -19.0,
                 ["تمام رنگ", "تمام‌رنگ", "کامل رنگ"],
                 research="بازار: 18-22%"),
            _adj("paint_roof", "سقف رنگ (شک برانگیز)", -12.0,
                 ["سقف رنگ", "سقف رنگ شده", "سقف دوررنگ"],
                 research="بازار: سقف رنگ = تصادف سنگین، 10-15% افت"),

            # شاسی — مهم‌ترین عامل
            _adj("chassis_small", "شاسی ضربه جزئی / سینی ضربه", -12.0,
                 ["شاسی ضربه جزئی", "سینی ضربه", "شاسی نوک ضربه"],
                 research="بازار: 10-15%"),
            _adj("chassis_hit", "شاسی ضربه / رنگ شاسی / تعویض سینی", -20.0,
                 ["شاسی ضربه", "شاسی رنگ", "شاسی خورده", "شاسی تعویض",
                  "سینی رنگ", "سینی تعویض", "شاسی چپی"],
                 home_block=False,
                 research="بازار: 18-25% — اگر 100km راه رفته ولی شاسی ضربه داشته باشد، با افت 20% هنوز ممکن است شکار باشد اگر قیمت 25% زیر میانه باشد"),
            _adj("chassis_pillar", "ستون ضربه / شاسی شدید", -28.0,
                 ["ستون خورده", "ستون ضربه", "ستون رنگ", "شاسی شدید", "اتاق جوش"],
                 research="بازار: 25-35% — معمولاً شکار نیست مگر خیلی ارزان"),

            # تصادف
            _adj("accident_light", "تصادف جزئی / صافکاری", -6.0,
                 ["تصادف جزئی", "صافکاری", "صافکاری بدون رنگ"],
                 research="بازار: 5-8%"),
            _adj("accident", "تصادفی / چپی", -18.0,
                 ["تصادفی", "چپی", "چپ کرده", "اتاق تعویض"],
                 research="بازار: 15-22%"),
            _adj("airbag", "ایربگ باز شده", -24.0,
                 ["ایربگ", "کیسه هوا باز", "ایربگ باز"],
                 research="بازار: 20-30% — افت سنگین"),

            # فنی
            _adj("mechanical_light", "ایراد فنی جزئی / واشر", -6.0,
                 ["واشر زده", "واشر سرسیلندر", "روغن ریزی"],
                 research="بازار: 5-8%"),
            _adj("mechanical", "ایراد موتوری / روغن سوزی", -12.0,
                 ["موتور تعمیر", "روغن سوزی", "یاتاقان", "سیلندر تراش", "موتور صدا"],
                 research="بازار: 10-15%"),
            _adj("engine_change", "تعویض موتور", -18.0,
                 ["تعویض موتور", "موتور تعویض", "موتور استوک"],
                 research="بازار: 15-20%"),
            _adj("gearbox", "گیربکس تعویض / اتومات خراب", -20.0,
                 ["گیربکس تعویض", "گیربکس خراب", "اتومات تقه", "گیربکس صدا"],
                 research="بازار: 18-25%"),

            # کارکرد و کاربری
            _adj("high_km", "کارکرد بالا (بالای ۱۵۰ هزار)", -5.0,
                 ["کارکرد بالا", "کارکرد زیاد"],
                 question="کارکرد بالا است؟",
                 research="بازار: هر 20 هزار کیلومتر بالای نرمال ~1% افت، ولی 100km vs صفر: صفر 3% گران‌تر است، پس 100km با قیمت مناسب هنوز شکار است"),
            _adj("very_high_km", "کارکرد خیلی بالا (۲۰۰k+)", -9.0,
                 ["کارکرد 200", "کارکرد 250", "کارکرد خیلی بالا"],
                 research="بازار: 8-12%"),
            _adj("taxi", "تاکسی / کار کرده / سرویس", -13.0,
                 ["تاکسی", "کارکرده سنگین", "سرویس مدارس", "تاکسی سابق"],
                 research="بازار: 10-15% — حتی تاکسی اگر خیلی ارزان باشد شکار است"),
            _adj("zero_km", "صفر کیلومتر / صفر خشک", 3.0,
                 ["صفر کیلومتر", "صفر خشک", "صفرکیلومتر", "خشک صفر"],
                 research="بازار: صفر 3-5% گران‌تر از 100km — پس 100km ارزان‌تر شکار محسوب می‌شود"),

            # بیمه و لاستیک
            _adj("no_insurance", "بیمه ندارد / تمام شده", -2.5,
                 ["بیمه ندارد", "بیمه تمام", "بدون بیمه"],
                 research="بازار: 2-3%"),
            _adj("short_insurance", "بیمه کوتاه (1-2 ماه)", -1.0,
                 ["بیمه 1 ماه", "بیمه 2 ماه", "بیمه کوتاه"],
                 research="بازار: 1%"),
            _adj("tires_new", "لاستیک نو / 4 حلقه نو", 1.5,
                 ["لاستیک نو", "چهار حلقه نو", "لاستیک 100%"],
                 research="بازار: +1-2%"),
        ],
    })
    return d


def _phone() -> Dict[str, Any]:
    d = dict(_SOFT)
    d.update(_PRO_HINT["phone"])
    d["good_pct"] = 10.0
    d["great_pct"] = 20.0
    d["suspicious_pct"] = 50.0
    d.update({
        "family": "phone",
        "hunter": True,
        "dealer_mode": False,
        "research_note": "بازار موبایل ایران ۱۴۰۳: باتری، رجیستری، کارتن، آب‌خوردگی بیشترین تاثیر",
        "warning": "موبایل — باتری زیر 80% و بدون کارتن و رجیستر افت زیاد دارد",
        "slots": [
            {"key": "storage", "label": "حافظه", "kind": "text",
             "ask": True, "critical": False,
             "question": "حافظه چند گیگ است؟ 64/128/256؟"},
            {"key": "condition", "label": "وضعیت بدنه", "kind": "enum",
             "ask": True, "critical": False,
             "question": "آکبند / در حد نو / خط‌وخش / ترک صفحه؟"},
            {"key": "battery", "label": "سلامت باتری", "kind": "text",
             "ask": True, "critical": False,
             "question": "سلامت باتری چقدر است؟ 90%؟"},
            {"key": "box", "label": "کارتن و لوازم", "kind": "enum",
             "ask": False, "critical": False,
             "question": "کارتن و شارژر دارد؟"},
        ],
        "adjustments": [
            _adj("like_new", "آکبند / پلمپ", 0.0,
                 ["آکبند", "پلمپ", "باز نشده", "سیل", "sealed"],
                 research="بازار: مبنا"),
            _adj("open_box", "در حد نو / کارتن باز", -3.0,
                 ["در حد نو", "درحد نو", "کارتن باز", "open box"],
                 research="بازار: 2-4% افت"),
            _adj("scratches", "خط و خش معمولی", -7.0,
                 ["خط و خش", "خط‌وخش", "خط خوردگی", "خش ریز"],
                 research="بازار: 5-8%"),
            _adj("cracked", "ترک ریز / شیشه شکسته", -22.0,
                 ["ترک", "شیشه شکسته", "ال سی دی شکسته", "ال‌سی‌دی شکسته",
                  "تاچ خراب", "صفحه شکسته", "گلس شکسته"],
                 research="بازار: 20-30% — حتی با ترک اگر خیلی ارزان باشد شکار است"),
            _adj("no_box", "بدون کارتن / بدون شارژر", -6.0,
                 ["بدون کارتن", "بی کارتن", "بدون شارژر", "شارژر ندارد"],
                 research="بازار: 5-7%"),
            _adj("no_register", "رجیستر نشده / همتا ندارد", -16.0,
                 ["رجیستر نیست", "همتا ندارد", "رجیستر نشده", "آنتن نمی‌دهد"],
                 research="بازار: 15-20% — افت سنگین"),
            _adj("battery_85", "باتری 85-90%", -4.0,
                 ["باتری 85", "باتری 88", "باتری 90", "سلامت 85"],
                 research="بازار: 3-5%"),
            _adj("battery_80", "باتری زیر 80% / ضعیف", -11.0,
                 ["باتری ضعیف", "باتری خراب", "باتری 75", "باتری 70", "سلامت پایین"],
                 research="بازار: 10-15% — باتری تعویض 10% افت"),
            _adj("water", "آب‌خوردگی", -26.0,
                 ["آب خورده", "آبخورده", "آب خوردگی", "رطوبت دیده"],
                 research="بازار: 25-35% — معمولاً شکار نیست مگر خیلی ارزان"),
            _adj("board", "تعمیر برد / آی‌سی", -32.0,
                 ["تعمیر برد", "برد تعمیری", "آی سی", "برد تعمیر", "هارد تعویض"],
                 research="بازار: 30-40% — ریسک بالا"),
            _adj("faceid", "فیس آیدی خراب / تاچ آیدی خراب", -14.0,
                 ["فیس آیدی خراب", "face id خراب", "تاچ آیدی خراب", "اثر انگشت خراب"],
                 research="بازار: 12-18%"),
            _adj("storage_low", "حافظه کم (64GB در مدل 256GB رایج)", -5.0,
                 ["64 گیگ", "حافظه 64", "64GB"],
                 research="بازار: 64GB نسبت به 256GB در آیفون 5-8% ارزان‌تر"),
        ],
    })
    return d


def _laptop() -> Dict[str, Any]:
    d = dict(_SOFT)
    d.update(_PRO_HINT["laptop"])
    d["good_pct"] = 10.0
    d["great_pct"] = 18.0
    d["suspicious_pct"] = 48.0
    d.update({
        "family": "laptop",
        "hunter": True,
        "dealer_mode": False,
        "research_note": "لپ‌تاپ: SSD vs HDD، رم، نسل CPU، باتری، صفحه",
        "slots": [
            {"key": "ram", "label": "رم", "kind": "text", "ask": True,
             "critical": False, "question": "رم چند گیگ است؟ 8/16؟"},
            {"key": "storage", "label": "حافظه SSD/HDD", "kind": "text",
             "ask": True, "critical": False, "question": "SSD است یا HDD؟ ظرفیت؟"},
            {"key": "cpu", "label": "نسل CPU", "kind": "text",
             "ask": False, "critical": False,
             "question": "CPU چیست؟ i5 نسل 11؟"},
            {"key": "opened", "label": "باز شده / آکبند", "kind": "enum",
             "ask": True, "critical": False,
             "question": "آکبند و بازنشده است یا کارکرده؟"},
        ],
        "adjustments": [
            _adj("unopened", "آکبند / باز نشده", 0.0,
                 ["آکبند", "باز نشده", "پلمپ", "در حد نو"],
                 research="مبنا"),
            _adj("opened", "کارکرده سالم", -6.0,
                 ["کارکرده", "استفاده شده", "دست دوم"],
                 research="6-10%"),
            _adj("hdd", "هارد HDD به‌جای SSD", -11.0,
                 ["هارد", "hdd", "مکانیکی", "بدون ssd"],
                 research="HDD نسبت به SSD 10-15% افت — حتی HDD اگر خیلی ارزان باشد شکار است"),
            _adj("ssd", "SSD", 0.0, ["اس اس دی", "ssd", "nvme"],
                 research="مبنا برای لپ‌تاپ 1403"),
            _adj("ram_4", "رم 4 گیگ (کم)", -7.0,
                 ["رم 4", "ram 4", "4 گیگ رم"],
                 research="رم 4 نسبت به 8: 5-10% افت"),
            _adj("no_charger", "بدون شارژر", -4.0,
                 ["بدون شارژر", "آداپتور ندارد", "شارژر ندارد"],
                 research="3-5%"),
            _adj("screen", "لکه / خط روی صفحه", -14.0,
                 ["لکه صفحه", "خط صفحه", "بک‌لایت", "پیکسل سوخته", "هاله صفحه"],
                 research="10-18% — صفحه گران است"),
            _adj("battery_weak", "باتری ضعیف / شارژ نگه نمی‌دارد", -8.0,
                 ["باتری ضعیف", "شارژ نگه نمیداره", "باتری خراب"],
                 research="5-10%"),
            _adj("keyboard", "کیبورد خراب / تاچ پد خراب", -6.0,
                 ["کیبورد خراب", "تاچ پد خراب", "صفحه کلید خراب"],
                 research="5-8%"),
        ],
    })
    return d


def _appliance() -> Dict[str, Any]:
    d = dict(_SOFT)
    d.update(_PRO_HINT["appliance"])
    d["good_pct"] = 12.0
    d["great_pct"] = 22.0
    d["suspicious_pct"] = 52.0
    d.update({
        "family": "appliance",
        "hunter": True,
        "research_note": "لوازم خانگی: نو vs کارکرده، بدون کارتن، تعمیری",
        "slots": [
            {"key": "condition", "label": "وضعیت", "kind": "enum",
             "ask": True, "critical": False,
             "question": "نو است یا کارکرده؟ ایراد دارد؟"},
            {"key": "warranty", "label": "گارانتی", "kind": "text",
             "ask": False, "critical": False,
             "question": "گارانتی دارد؟"},
        ],
        "adjustments": [
            _adj("new", "نو / آکبند", 0.0, ["نو", "آکبند", "باز نشده"],
                 research="مبنا"),
            _adj("used", "کارکرده سالم", -8.0, ["کارکرده", "استفاده شده", "دست دوم"],
                 research="5-12% بسته به لوازم"),
            _adj("like_new", "در حد نو", -3.0, ["در حد نو", "درحد نو"],
                 research="2-4%"),
            _adj("no_box", "بدون کارتن", -4.0, ["بدون کارتن", "بی کارتن"],
                 research="3-5%"),
            _adj("repair", "تعمیری / نیاز به تعمیر", -22.0,
                 ["تعمیری", "نیاز به تعمیر", "خراب", "سوخته", "نیم سوز"],
                 research="20-30% — لوازم تعمیری ریسک بالا"),
            _adj("no_warranty", "بدون گارانتی", -3.0,
                 ["بدون گارانتی", "گارانتی ندارد", "بی گارانتی"],
                 research="2-4%"),
        ],
    })
    return d


def _generic() -> Dict[str, Any]:
    d = dict(_SOFT)
    d.update(_PRO_HINT["generic"])
    d["good_pct"] = 10.0
    d["great_pct"] = 20.0
    d["suspicious_pct"] = 50.0
    d.update({
        "family": "generic",
        "hunter": True,
        "research_note": "عمومی: نو/کارکرده/معیوب",
        "slots": [
            {"key": "condition", "label": "وضعیت کالا", "kind": "enum",
             "ask": True, "critical": False,
             "question": "نو / در حد نو / کارکرده / معیوب؟"},
        ],
        "adjustments": [
            _adj("unopened", "باز نشده / آکبند", 0.0, ["آکبند", "پلمپ", "باز نشده"],
                 research="مبنا"),
            _adj("like_new", "در حد نو", -3.0, ["در حد نو", "درحد نو"],
                 research="2-4%"),
            _adj("used", "کارکرده", -8.0, ["کارکرده", "دست دوم", "استفاده شده"],
                 research="5-12%"),
            _adj("defect_soft", "ایراد جزئی / خط و خش", -12.0,
                 ["خط و خش", "لکه", "تعمیر جزئی", "خش"],
                 research="10-15%"),
            _adj("defect_hard", "معیوب / شکسته", -28.0,
                 ["شکسته", "معیوب", "خراب", "سوخته"],
                 research="25-35% — حتی معیوب اگر خیلی ارزان باشد ممکن است شکار باشد برای قطعات"),
        ],
    })
    return d


def _estate() -> Dict[str, Any]:
    return {
        "family": "real_estate",
        "hunter": False,
        "reason": "املاک در شکارچی پشتیبانی نمی‌شود — خیلی پیچیده است (متراژ، منطقه، سند، وام...)",
        "warning": "املاک شکار نمی‌شود — فقط شماره پیدا می‌کند، قیمت را تحلیل نمی‌کند",
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
    "vacuum-cleaner": "appliance",
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
    ("vacuum-cleaner", ("جاروبرقی", "جارو برقی", "vacuum")),
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


def _normalize_custom_adj(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """آپشن سفارشی کاربر → فرمت استاندارد adjustment."""
    if not isinstance(item, dict):
        return None
    key = str(item.get("key") or item.get("id") or "").strip()
    if not key:
        # از label بساز
        label = str(item.get("label") or "").strip()
        if not label:
            return None
        key = re.sub(r"\W+", "_", normalize(label))[:32] or "custom"
    label = str(item.get("label") or key).strip() or key
    try:
        pct = float(item.get("pct") or item.get("percent") or 0)
    except (TypeError, ValueError):
        pct = 0.0
    # pct باید بین -50 و +10 باشد
    pct = max(-50.0, min(10.0, pct))
    words = item.get("words") or item.get("keywords") or []
    if isinstance(words, str):
        words = [w.strip() for w in words.split(",") if w.strip()]
    if not isinstance(words, list):
        words = []
    question = str(item.get("question") or f"{label}؟").strip()
    ask = bool(item.get("ask", True))
    research = str(item.get("research") or "سفارشی کاربر").strip()
    return {
        "key": key,
        "label": label,
        "pct": pct,
        "words": [str(w) for w in words if w],
        "ask": ask,
        "home_block": bool(item.get("home_block", False)),
        "question": question,
        "research": research,
        "custom": True,
    }


def merge_overrides(profile: Dict[str, Any],
                    overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """درصدها و آستانه‌های کاربر روی پیش‌فرض — حالا آپشن جدید هم اضافه می‌کند."""
    out = copy.deepcopy(profile or default_profile())
    if not overrides or not isinstance(overrides, dict):
        return out
    for k in ("good_pct", "great_pct", "suspicious_pct", "dealer_mode",
              "km_per_year", "year_depreciation_per_year"):
        if k in overrides and overrides[k] not in (None, ""):
            if k == "dealer_mode":
                out[k] = bool(overrides[k])
            else:
                try:
                    out[k] = float(overrides[k])
                except (TypeError, ValueError):
                    pass

    # حالت قدیمی: dict key->pct
    user_adj = overrides.get("adjustments")
    custom_list = overrides.get("custom_adjustments") or overrides.get("custom") or []

    by = {a["key"]: a for a in out.get("adjustments") or []}

    if isinstance(user_adj, dict):
        for key, val in user_adj.items():
            if isinstance(val, dict):
                # {key: {pct, label, words}}
                norm = _normalize_custom_adj({"key": key, **val})
                if norm:
                    by[key] = {**by.get(key, {}), **norm} if key in by else norm
            else:
                # {key: pct}
                if key in by:
                    try:
                        by[key]["pct"] = float(val)
                    except (TypeError, ValueError):
                        pass
                else:
                    # آپشن جدید با فقط درصد — label از key
                    try:
                        by[key] = _normalize_custom_adj({"key": key, "pct": float(val), "label": key})
                    except (TypeError, ValueError):
                        pass
    elif isinstance(user_adj, list):
        for item in user_adj:
            if not isinstance(item, dict):
                continue
            norm = _normalize_custom_adj(item)
            if not norm:
                continue
            key = norm["key"]
            if key in by:
                # اگر موجود است، pct و ... را به‌روز کن
                by[key].update({k: v for k, v in norm.items() if v not in (None, "", []) or k == "pct"})
            else:
                by[key] = norm

    # custom_adjustments جدا — همیشه اضافه
    if isinstance(custom_list, list):
        for item in custom_list:
            norm = _normalize_custom_adj(item)
            if not norm:
                continue
            by[norm["key"]] = norm

    out["adjustments"] = list(by.values())
    return out


def public_for_ui(profile: Dict[str, Any]) -> Dict[str, Any]:
    """برای پاپ‌آپ تنظیمات پیشرفته — حالا research و custom هم دارد."""
    return {
        "category": profile.get("category") or "",
        "family": profile.get("family") or "generic",
        "hunter": bool(profile.get("hunter", True)),
        "reason": profile.get("reason") or "",
        "warning": profile.get("warning") or "",
        "research_note": profile.get("research_note") or "",
        "good_pct": float(profile.get("good_pct") or 8),
        "great_pct": float(profile.get("great_pct") or 15),
        "suspicious_pct": float(profile.get("suspicious_pct") or 55),
        "dealer_mode": bool(profile.get("dealer_mode")),
        "km_per_year": float(profile.get("km_per_year") or 20000),
        "year_depreciation_per_year": float(profile.get("year_depreciation_per_year") or 5.0),
        "slots": list(profile.get("slots") or []),
        "adjustments": [
            {"key": a["key"], "label": a["label"], "pct": a["pct"],
             "ask": bool(a.get("ask")), "question": a.get("question") or "",
             "research": a.get("research") or "",
             "custom": bool(a.get("custom")),
             "words": a.get("words") or []}
            for a in (profile.get("adjustments") or [])
        ],
        "hint": profile.get("warning") or (
            "پیش‌فرض‌ها نرم‌اند تا چند شکار پیدا شود. "
            "اگر کاسب حرفه‌ای هستید درصد افت را کمی بیشتر کنید. "
            "می‌توانید آپشن جدید اضافه کنید — مثلاً 'کف‌خواب' یا 'باتری تعویض'."),
        "pro_hint": _PRO_HINT.get(profile.get("family") or "generic") or _SOFT,
    }


def extract_flags(text: str, profile: Dict[str, Any]) -> Dict[str, bool]:
    n = normalize(text or "")
    found: Dict[str, bool] = {}
    for a in profile.get("adjustments") or []:
        words = a.get("words") or []
        found[a["key"]] = any(normalize(w) in n for w in words if w)
    return found


def adjustment_pct(flags: Dict[str, bool], profile: Dict[str, Any]) -> float:
    """جمع افت (منفی). سقف −۴۵٪ تا سخت‌گیر نباشد ولی دقیق‌تر از قبل."""
    total = 0.0
    for a in profile.get("adjustments") or []:
        if flags.get(a["key"]):
            total += float(a.get("pct") or 0)
    # سقف جدید: -45% تا +5% (قبلاً -35%)
    return max(-45.0, min(5.0, total))


def mileage_adjustment(mileage_km: Optional[int], year: Optional[int],
                       km_per_year: float = 20000) -> float:
    """افت بر اساس کارکرد نسبت به سال — هر 20 هزار کیلومتر بالای نرمال 1% افت.

    مثال: خودرو 1399 (4 سال پیش) → نرمال 80k، اگر 100k باشد 20k اضافه → 1% افت.
    صفر خشک (0km) → +3% نسبت به 100km — پس 100km ارزان‌تر شکار محسوب می‌شود.
    """
    if mileage_km is None:
        return 0.0
    try:
        km = int(mileage_km)
    except (TypeError, ValueError):
        return 0.0
    if km == 0:
        return 3.0
    if km < 0:
        return 0.0
    mileage_km = km
    if not year:
        # بدون سال: بالای 150k افت
        if mileage_km > 200000:
            return -9.0
        if mileage_km > 150000:
            return -5.0
        return 0.0
    try:
        from datetime import datetime
        # سال شمسی به میلادی تقریبی
        if year > 1300:
            age = max(0, 1404 - int(year))  # 1404 امسال
        else:
            age = max(0, 2025 - int(year))
    except Exception:
        age = 3
    expected = max(10000, age * km_per_year)
    extra = mileage_km - expected
    if extra <= 0:
        # کمتر از نرمال — کمی مثبت
        if mileage_km < 5000:
            return 3.0
        if mileage_km < 20000:
            return 1.0
        return 0.0
    # هر 20k اضافه = 1% افت
    pct = -(extra / 20000.0)
    return max(-12.0, pct)


def year_adjustment(year: Optional[int], depreciation_per_year: float = 5.0) -> float:
    """افت سال — برای محاسبه ارزش منصفانه، نه برای adjustment_pct.

    این تابع جدا استفاده می‌شود: fair = median * (1 + year_factor)
    """
    if not year:
        return 0.0
    try:
        if year > 1300:
            age = max(0, 1404 - int(year))
        else:
            age = max(0, 2025 - int(year))
    except Exception:
        return 0.0
    # هر سال 5% افت نسبت به امسال
    return -(age * depreciation_per_year)


def missing_ask_slots(text: str, profile: Dict[str, Any],
                      extra: Optional[Dict[str, Any]] = None) -> List[str]:
    """اسلات‌هایی که برای سؤال لازم‌اند و در متن نیستند."""
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
        if key == "paint" and extra.get("paint") in ("clean", "repainted", "panel", "full"):
            continue
        if key in ("paint", "chassis") and any(flags.values()):
            continue
        if key == "condition" and any(flags.values()):
            continue
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
    """اسلات از پاسخ فروشنده — قاعده + کارکرد و سال."""
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
        # کارکرد و سال → افت جدا
        out["mileage_adj"] = mileage_adjustment(out.get("mileage_km"), out.get("year"),
                                                profile.get("km_per_year") or 20000)
    price = parse_toman(text)
    if price and price >= 10_000:
        out["price_toman"] = price
    if any(w in n for w in ("سالمه", "شاسی سالم", "بی رنگ", "بیرنگ")):
        out.setdefault("chassis", "ok")
    return out
