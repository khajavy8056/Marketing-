# -*- coding: utf-8 -*-
"""تنظیمات شکارچی با کمک AI — چت خودمونی پرانرژی، منعطف، قدم به قدم.

هدف: کاربر بگه "دنبال مچ دستگاهی آیفون X 12 13 14 15 قیمت خوب بخریم"
و ربات مثل رفیق تهرانی، باحال، خودمونی، قدم به قدم بپرسه:
- چه مدل‌ها دقیق
- قیمت فروش سالم هر مدل
- سود مطلوب هر دستگاه
- تعداد
- شرایط

ویژگی‌ها:
- در هر پیام، تعداد و شرایط را هم استخراج می‌کند (حتی اگر وسط مرحله دیگری باشد)
- اگر کاربر دو عدد با هم بدهد "20 میفروشم 3 سود" هر دو را می‌گیرد
- مکالمه پیش‌بینی نشده (سلام، چطوری، ممنون، نمی‌دونم) را می‌فهمد و دوستانه جواب می‌دهد
- فقط یک سوال در هر پیام، نه همه چیز با هم
"""

from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Optional, Tuple

from .matching import normalize

# ------------------------------------------------------ الگوها و استخراج
IPHONE_PATTERN = re.compile(r"(?:iphone|آیفون)\s*([0-9]{1,2})\s*(?:pro\s*max|pro|plus|mini|promax)?", re.I)
IPHONE_FA_PATTERN = re.compile(r"آیفون\s*([0-9]{1,2})", re.I)

BRAND_MODELS = {
    "iphone": ["آیفون", "iphone"],
    "samsung": ["سامسونگ", "samsung", "گلکسی", "galaxy"],
    "xiaomi": ["شیائومی", "xiaomi", "redmi", "poco"],
    "laptop": ["لپ تاپ", "لپ‌تاپ", "لپتاپ", "نوت بوک", "macbook", "مک بوک"],
    "pride": ["پراید", "111", "131", "132"],
}


def _parse_price_to_toman(text: str) -> Optional[int]:
    if not text:
        return None
    t = text.replace("،", ",").strip()
    m = re.search(r"(\d+(?:[\d,\.,]*\d+)?)\s*(میلیون|تومن|تومان|هزار|m|k)?", t, re.I)
    if not m:
        return None
    num_s = m.group(1).replace(",", "").replace("،", "")
    try:
        # keep decimal dot for like 2.5
        # Persian dot? replace Arabic decimal?
        # Allow one dot
        if num_s.count(".") > 1:
            num_s = num_s.replace(".", "")
        num = float(num_s)
    except:
        return None
    unit = (m.group(2) or "").lower()
    if "میلیون" in unit or unit == "m":
        return int(num * 1_000_000)
    if "هزار" in unit or unit == "k":
        return int(num * 1000)
    # اگر واحد ندارد و عدد کوچک است، میلیون فرض کن، ولی اعشار را نگه دار
    if num < 1000:
        return int(num * 1_000_000)
    return int(num)


def parse_all_price_candidates(text: str, current_model: str = "") -> List[Tuple[int, bool, str]]:
    """برگرداندن لیست (value_toman_or_percent, is_percent, raw) به ترتیب ظاهر.
    current_model برای حذف عدد مدل مثل 12 در 'آیفون 12' استفاده می‌شود."""
    if not text:
        return []
    # برای حذف عدد مدل: اگر متن شامل 'آیفون 12' باشد، 12 را به عنوان قیمت حساب نکن مگر واحد داشته باشد
    model_numbers = set()
    for mm in re.finditer(r"(?:iphone|آیفون)\s*([0-9]{1,2})", text, re.I):
        try:
            model_numbers.add(int(mm.group(1)))
        except:
            pass
    # همچنین عدد مدل فعلی را اضافه کن
    if current_model:
        for mm in re.finditer(r"([0-9]{1,2})", current_model):
            try:
                model_numbers.add(int(mm.group(1)))
            except:
                pass

    ordered: List[Tuple[int, int, bool, str]] = []
    for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(میلیون|تومن|تومان|هزار|درصد|%|percent)?", text, re.I):
        raw = m.group(0)
        start = m.start()
        # چک کن آیا این عدد مدل است و بدون واحد
        num_part = re.search(r"\d+(?:[.,]\d+)?", raw)
        if not num_part:
            continue
        try:
            num_val = float(num_part.group(0).replace(",", ""))
        except:
            continue
        is_pct = bool(re.search(r"درصد|%|percent", raw, re.I))
        # اگر عدد مدل است و واحد ندارد و درصد نیست، رد کن
        if not is_pct and not re.search(r"میلیون|تومن|تومان|هزار", raw, re.I):
            # اگر عدد صحیح کوچک و در model_numbers است، و قبلش آیفون آمده، رد کن
            if int(num_val) in model_numbers:
                # بررسی کن آیا قبل از این مچ، کلمه آیفون/iphone آمده (تا 10 کاراکتر قبل)
                prev = text[max(0, start - 12):start].lower()
                if "آیفون" in prev or "iphone" in prev or "آیفون" in text[max(0, start-20):start+5]:
                    # اگر این اولین وقوع است و دقیقا مدل است، رد کن
                    # ولی اگر بعدش کلمه فروش/سود باشد و عدد مدل نباشد، نگه دار
                    # ساده: اگر عدد مدل و بدون واحد و متن شامل فروش/سود است، ولی فاصله تا آیفون کم است، رد کن
                    if int(num_val) in model_numbers and int(num_val) <= 15:
                        # اگر در کل متن فقط یک عدد مدل باشد و بقیه عددها بزرگتر، این را رد کن
                        # چک: آیا این مچ دقیقا بعد از آیفون است؟
                        if re.search(r"(?:iphone|آیفون)\s*$", prev, re.I):
                            continue
        if is_pct:
            try:
                v = float(re.search(r"\d+(?:\.\d+)?", raw).group(0))
                if 1 <= v <= 80:
                    ordered.append((start, int(v), True, raw))
            except:
                pass
        else:
            val = _parse_price_to_toman(raw)
            if val and val >= 500_000:
                # اگر عدد مدل است و بدون واحد و کمتر از 16، و دقیقا مساوی مدل، رد کن (مگر اینکه واحد داشته باشد)
                if not re.search(r"میلیون|تومن|تومان|هزار", raw, re.I):
                    if int(num_val) in model_numbers and int(num_val) <= 16:
                        # اگر این عدد دقیقا بعد از آیفون است، رد کن
                        prev2 = text[max(0, start - 15):start]
                        if re.search(r"(?:iphone|آیفون)\s*$", prev2.strip(), re.I):
                            continue
                ordered.append((start, val, False, raw))
    ordered.sort(key=lambda x: x[0])
    # حذف تکراری‌های پشت سر هم با مقدار یکسان
    dedup: List[Tuple[int, bool, str]] = []
    seen_vals = set()
    for _, v, is_pct, raw in ordered:
        # اگر قبلا همین مقدار با همین نوع دیده شده و فاصله کم است، رد کن
        key = (v, is_pct)
        # ولی برای قیمت‌های متفاوت نگه دار
        dedup.append((v, is_pct, raw))
    return dedup


def extract_products_from_text(text: str) -> List[Dict[str, Any]]:
    if not text:
        return []
    n = normalize(text)
    products: List[Dict[str, Any]] = []
    seen_models = set()
    iphone_strong = re.compile(
        r"(?:iphone|آیفون)\s*(X[SR]?|XS\s*Max|1[0-5]|1[0-2])\s*(Pro\s*Max|Pro|Plus|Mini|promax)?", re.I
    )
    for m in iphone_strong.finditer(text):
        ver = (m.group(1) or "").strip()
        extra = (m.group(2) or "").strip()
        ver_clean = ver.replace(" ", "").upper() if ver.upper().startswith("X") else ver
        if ver_clean.lower().startswith("xs"):
            ver_clean = "XS"
        full = f"آیفون {ver_clean}"
        if extra:
            ex_low = extra.lower().replace(" ", "")
            if "promax" in ex_low or "pro max" in extra.lower():
                full = f"آیفون {ver_clean} Pro Max"
            elif "pro" in ex_low:
                full = f"آیفون {ver_clean} Pro"
            elif "plus" in ex_low:
                full = f"آیفون {ver_clean} Plus"
            elif "mini" in ex_low:
                full = f"آیفون {ver_clean} Mini"
        if full not in seen_models:
            seen_models.add(full)
            products.append(
                {
                    "model": full,
                    "brand": "apple",
                    "family": "phone",
                    "keyword": full,
                    "category": "mobile-phones",
                }
            )
    for m in IPHONE_PATTERN.finditer(text):
        ver = m.group(1)
        full = f"آیفون {ver}"
        extra = m.group(0).lower()
        if "pro max" in extra or "promax" in extra:
            full = f"آیفون {ver} Pro Max"
        elif "pro" in extra:
            full = f"آیفون {ver} Pro"
        elif "plus" in extra:
            full = f"آیفون {ver} Plus"
        elif "mini" in extra:
            full = f"آیفون {ver} Mini"
        if full not in seen_models:
            seen_models.add(full)
            products.append(
                {
                    "model": full,
                    "brand": "apple",
                    "family": "phone",
                    "keyword": full,
                    "category": "mobile-phones",
                }
            )
    if products or "آیفون" in text or "iphone" in text.lower():
        nums = re.findall(r"(?<!\w)(X[SR]?|1[0-5]|1[0-2])(?!\w)", text, re.I)
        for num in nums:
            num_clean = num.strip().upper() if num.upper().startswith("X") else num.strip()
            full = f"آیفون {num_clean}"
            if full not in seen_models:
                seen_models.add(full)
                products.append(
                    {
                        "model": full,
                        "brand": "apple",
                        "family": "phone",
                        "keyword": full,
                        "category": "mobile-phones",
                    }
                )
    if not products:
        kw = text.strip()[:80]
        if len(kw) >= 2:
            fam = "generic"
            cat = ""
            if any(normalize(w) in n for w in BRAND_MODELS["iphone"]):
                fam = "phone"
                cat = "mobile-phones"
            elif any(normalize(w) in n for w in BRAND_MODELS["samsung"]):
                fam = "phone"
                cat = "samsung"
            elif any(normalize(w) in n for w in BRAND_MODELS["laptop"]):
                fam = "laptop"
                cat = "laptops"
            elif any(normalize(w) in n for w in BRAND_MODELS["pride"]):
                fam = "vehicle"
                cat = "light"
            # اگر کلمه خیلی عمومی بود مثل "سلام" نگیریم
            if len(kw) > 2 and not any(x in normalize(kw) for x in ["سلام", "چطور", "خوبی", "مرسی"]):
                products.append(
                    {
                        "model": kw,
                        "brand": "",
                        "family": fam,
                        "keyword": kw,
                        "category": cat,
                    }
                )
    return products


def extract_numbers(text: str) -> List[int]:
    out = []
    for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(میلیون|تومان|هزار|درصد|%|m)?", text):
        val = _parse_price_to_toman(m.group(0))
        if val:
            out.append(val)
    return out


def extract_quantity(text: str) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"(\d+)\s*(?:تا|عدد|دونه)", text)
    if m:
        try:
            v = int(m.group(1))
            if 1 <= v <= 1000:
                return v
        except:
            pass
    m = re.search(r"هر\s*مدل\s*(\d+)", text)
    if m:
        try:
            return int(m.group(1))
        except:
            pass
    m = re.search(r"تعداد[:\s]*(\d+)", text)
    if m:
        try:
            return int(m.group(1))
        except:
            pass
    if any(w in text for w in ["تا میخوام", "تا بخریم", "تعداد", "هر مدل"]):
        nums = re.findall(r"\b(\d{1,3})\b", text)
        for ns in nums:
            try:
                v = int(ns)
                if 1 <= v <= 100:
                    return v
            except:
                pass
    # standalone small number in quantity context
    if any(w in text for w in ["بخرم", "میخوام", "بگیر"]):
        m = re.search(r"\b([1-9][0-9]?)\b", text)
        if m:
            # only if no million word
            if "میلیون" not in text and "سود" not in text and "فروش" not in text:
                try:
                    v = int(m.group(1))
                    if 1 <= v <= 50:
                        return v
                except:
                    pass
    return None


def extract_conditions(text: str) -> List[str]:
    if not text:
        return []
    parts = re.split(r"[،,]\s*|\s+و\s+", text)
    conds = []
    keywords = [
        "تمیز",
        "بدون تعمیر",
        "بدون خط",
        "سالم",
        "باتری",
        "کارکرده",
        "نو",
        "بدون خش",
        "پلمپ",
        "رجیستر",
        "بدون رجیستر",
        "اصل",
        "فابریک",
        "بدون تعویض",
        "خط و خش",
        "تمیز باشه",
        "تعمیر نشده",
    ]
    for p in parts:
        pp = p.strip()
        if not pp:
            continue
        if any(k in pp for k in keywords) or ("باتری" in pp):
            if "میلیون" in pp or "سود" in pp or "قیمت" in pp:
                continue
            if pp not in conds and len(pp) >= 2 and len(pp) <= 60:
                conds.append(pp)
    # also direct keyword search
    for k in keywords:
        if k in text and not any(k in c for c in conds):
            if len(k) > 2:
                conds.append(k)
    # battery percent like "باتری بالای 85"
    m = re.search(r"باتری.*?(?:بالای|بیشتر|over)?\s*(\d{2,3})", text)
    if m:
        phrase = f"باتری بالای {m.group(1)}"
        if phrase not in conds:
            conds.append(phrase)
    return conds[:8]


# ------------------------------------------------------ تشخیص نیت و احوالپرسی
SMALL_TALK_GREET = ["سلام", "درود", "سلا", "هلو", "hello", "hi", "چطوری", "چخبر", "خوبی"]
SMALL_TALK_THANKS = ["مرسی", "ممنون", "دمت گرم", "thanks", "thank", "عالی", "دستت درد نکنه"]
SMALL_TALK_CONFUSED = ["نمی‌دونم", "نمیدونم", "چی", "متوجه نشدم", "چجوری", "چطور", "راهنمایی"]
AFFIRMATIVE = ["اوکی", "ok", "باشه", "درسته", "آره", "ست کن", "تایید", "حله", "بزن", "انجام بده", "اوکیه"]
NEGATIVE = ["نه", "نمیخوام", "بیخیال", "کنسل", "صبر کن"]

def is_greeting(t: str) -> bool:
    nt = normalize(t)
    return any(normalize(w) in nt for w in SMALL_TALK_GREET)

def is_thanks(t: str) -> bool:
    nt = normalize(t)
    return any(normalize(w) in nt for w in SMALL_TALK_THANKS)

def is_confused(t: str) -> bool:
    nt = normalize(t)
    return any(normalize(w) in nt for w in SMALL_TALK_CONFUSED)

def is_affirmative(t: str) -> bool:
    nt = normalize(t)
    return any(normalize(w) in nt for w in AFFIRMATIVE)

def is_negative(t: str) -> bool:
    nt = normalize(t)
    return any(normalize(w) in nt for w in NEGATIVE)


# ------------------------------------------------------ پیام‌های خودمونی باحال
GREETINGS = [
    "سلام رفیقِ گل 😍 چه انرژی خفنی! من سلفمونی، شکارچی دیوارتام! قراره با هم بترکونیم بازارو 🚀",
    "ای جان! 😎 اومدی که یه سود مشتی ببریم؟ من اینجام، بگو چی تو ذهنته داداش!",
    "درود به مرامِت 🌹 خوش اومدی! امروز قراره با هم یه شکار حسابی بزنیم، آماده‌ای؟",
    "سلام سلام! 👋 دمت گرم اومدی! بگو ببینم امروز دنبال چی هستیم که سود کنیم؟",
    "به به! رفیقِ خودم اومد 😍 بگو چی می‌خوای بخری که قیمت خوب گیر بیاریم؟",
]

ASK_PRODUCTS = [
    "خب رفیق، اول بگو دقیقاً دنبال چه دستگاهایی هستی؟ مثلاً بگو «آیفون 12 13 14 15» یا هرچی تو ذهنته، همینجوری خودمونی بنویس 👇",
    "باشه، بریم سر اصل مطلب 😎 چه مدلایی مد نظرته؟ آیفون؟ سامسونگ؟ لپ‌تاپ؟ هرچی هست راحت بگو، من می‌فهمم!",
    "یه لیست بده بهم عشقم! مثلا بگو «آیفون X 12 13» یا «پراید 131 تمیز». هرچی می‌خوای شکار کنم همینجا بنویس 🔥",
]

ASK_SELL_PRICE = [
    "ایول! {model} انتخاب خفنیه 🔥 ببین داداش، به شرط سالم و تمیز، الان تو بازار چقدر می‌تونی بفروشیش؟ مثلا 40 میلیون؟ یه عدد بده 💰",
    "دمت گرم! {model} رو گرفتم ✅ حالا بهم بگو اگه سالم باشه، خودت حدودا چقدر می‌فروشیش؟ مثلا بگو 25 میلیون",
    "{model} 😍 عالیه! قیمت فروشِ سالمش چقدره به نظرت؟ مثلا تو دیوار چقدر میره؟ یه عدد بگو تا حساب کنم",
    "خب {model} رو داریم! حالا قیمتِ فروشِ تمیزش چنده؟ مثلا بگو 30 میلیون میره",
]

ASK_PROFIT = [
    "حالا سوال طلایی! 💡 رو {model} چقدر می‌خوای سود کنی؟ مثلا بگو 3 میلیون، یا بگو 10 درصد؟ هرجور راحتی بگو 🎯",
    "سودش چقدر باشه حال می‌کنی؟ 😎 رو {model} مثلا 2 تا 5 میلیون؟ یا مثلا 15% ؟ بگو تا تنظیم کنم",
    "باشه، {model} فروشش ~{sell}، حالا چقدر سود برات خوبه؟ مثلا بگو 4 میلیون بمونه برام",
    "خفن! حالا بگو رو {model} چند سود کنیم که به‌صرفه باشه؟ مثلا 3 میلیون؟",
]

ASK_QUANTITY = [
    "چند تا {model} می‌خوای؟ مثلا بگو 2 تا، یا هرچی قیمت خوب بود بگیرم؟ 🔢",
    "تعدادش چطور داداش؟ هر مدل چند تا می‌خوای شکار کنم؟ مثلا بگو هر کدوم 5 تا",
    "بگو ببینم، کلا چند تا می‌خوای بخری؟ مثلا ماهی 3 تا؟ یا هرچی گیر اومد؟",
    "هر مدل چند تا بگیریم؟ مثلا بگو «هر مدل 5 تا» یا «کلا 10 تا»",
]

ASK_CONDITIONS = [
    "شرایطش چطور باشه عشقم؟ مثلا میگی فقط تمیز و بدون تعمیر؟ یا باتری بالای 85؟ هر شرطی داری بگو تا فقط همونارو بیارم 🧹✨",
    "چه شرایطی برات مهمه؟ بدون خط و خش؟ بدون تعمیر؟ باتری بالا؟ بگو تا فیلتر کنم",
    "دستگاه چجوری باشه می‌پسندی؟ مثلا تمیز، بدون تعمیر، باتری خوب؟ هرچی مد نظرته بگو",
    "شرایط خاصی داری؟ مثلا میگی پلمپ باشه یا کارکرده تمیز هم اوکیه؟",
]

CONFIRM_TEMPLATES = [
    "خب بذار ببینم درست فهمیدم رفیق 👇\n",
    "دمت گرم! این چیزیه که من گرفتم، چک کن ببین درسته؟ 👇\n",
    "ایول! ببین این خلاصه‌شه، درسته؟ 👇\n",
]

FINAL_OK = [
    "ترکوندی رفیق! 🚀 تنظیماتت آماده‌ست! الان دکمه «⭐ ست کردن تنظیمات» رو بزن تا خودکار همه چی ست بشه. از این به بعد شکارچی با همین سود و قیمت برات می‌گرده، هم دیوار هم شیپور! 🔥",
    "حله داداش! ✅ همه چی رو گرفتم، تنظیمات حرفه‌ای‌ت آماده‌ست! فقط دکمه پایین رو بزن تا ست بشه. اگه چیزی جا مونده بگو تا اضافه کنم 🙏",
    "عالی شد 😍 بزن بریم! دکمه ست کردن رو بزن تا شکار شروع شه. منم همین بغل می‌مونم اگه چیزی خواستی بگی!",
]

SMALL_TALK_REPLIES = [
    "قربونت داداش 😎 من اینجام که بترکونیم! بریم ادامه بدیم؟",
    "دمت گرم انرژی میدی! 🔥 خب برگردیم به شکار؟",
    "ایول به مرامت! حالا بگو بریم چی کار کنیم؟",
]

CONFUSED_REPLIES = [
    "ببین رفیق، ساده‌ست 😊 فقط بگو مثلا «آیفون 12 13» یا یه عدد مثل «20 میلیون». من خودم بقیه‌شو می‌فهمم!",
    "نگران نباش! هرچی تو ذهنته همینجوری بنویس، من می‌فهمم. مثلا بگو «20 میلیون میفروشم» یا «3 میلیون سود»",
]

def _pick(arr: List[str]) -> str:
    return random.choice(arr)

def _is_model_ready() -> bool:
    try:
        from .nlu_model import is_ready, backend_name
        if not is_ready():
            return False
        bn = backend_name()
        if bn == "none":
            return False
        if "fallback" in bn:
            return False
        return True
    except Exception:
        return False

def _llm_chat(prompt: str) -> str:
    try:
        from .nlu_model import gguf_path, llama_exe, _has_llama_cpp_python
        import subprocess, sys
        full_prompt = (
            "تو یک دستیار خرید و فروش حرفه‌ای، صمیمی، پرانرژی، تهرانی هستی.\n"
            "کاربر می‌خواد دستگاه دست دوم بخره و بفروشه سود کنه.\n"
            "خیلی خودمونی، با ایموجی، با انرژی صحبت کن. مثل رفیق. داداش، رفیق، عشقم بگو.\n"
            "سوال رو کوتاه بپرس، نه طولانی. فقط یک سوال.\n"
            f"متن کاربر: {prompt}\n"
            "پاسخ تو (فارسی، خودمونی، کوتاه):"
        )
        if _has_llama_cpp_python():
            try:
                from llama_cpp import Llama
                g = gguf_path()
                model = Llama(model_path=str(g), n_ctx=1024, n_threads=4, verbose=False)
                out = model.create_completion(prompt=full_prompt, max_tokens=180, temperature=0.85, stop=["\n\n"])
                txt = (out.get("choices") or [{}])[0].get("text") or ""
                txt = txt.strip()
                if txt:
                    return txt[:400]
            except Exception:
                pass
        exe = llama_exe()
        g = gguf_path()
        if exe and g.exists():
            cmd = [str(exe), "-m", str(g), "-n", "180", "-c", "1024", "--temp", "0.85", "-p", full_prompt, "-no-cnv"]
            try:
                r = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=20,
                    creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if sys.platform == "win32" else 0,
                )
                out = (r.stdout or b"").decode("utf-8", errors="replace")
                if full_prompt in out:
                    out = out.split(full_prompt)[-1]
                out = out.strip().split("\n")[0].strip()
                if out:
                    return out[:400]
            except Exception:
                pass
    except Exception:
        pass
    return ""


def generate_ai_message(step: str, context: Dict[str, Any]) -> str:
    # سعی کن با LLM محلی اگر آماده است
    if _is_model_ready():
        try:
            prompt_map = {
                "greeting": "کاربر تازه اومده، سلام پرانرژی خودمونی تهرانی بگو و بپرس دنبال چی هستی برای خرید و فروش",
                "ask_products": f"کاربر گفت: {context.get('last_user','')}. بپرس دقیقا چه مدلایی مد نظرشه، خیلی خودمونی",
                "ask_sell_price": f"مدل {context.get('model','')} انتخاب شده. بپرس به شرط سالم چقدر می‌تونه بفروشه، خودمونی",
                "ask_profit": f"مدل {context.get('model','')} قیمت فروش {context.get('sell_price','')}. بپرس چقدر سود می‌خواد، یک سوال",
                "ask_quantity": f"مدل {context.get('model','')} سود {context.get('profit','')}. بپرس چند تا می‌خواد، خودمونی",
                "ask_conditions": "بپرس شرایط دستگاه چطور باشه، خیلی کوتاه و باحال",
                "confirm": "جمع‌بندی کن چی فهمیدی و بپرس اوکیه، خودمونی",
                "done": "بگو تنظیمات آماده‌ست و دکمه ست کردن رو بزنه، با هیجان",
                "small_talk": f"کاربر گفت: {context.get('last_user','')}. جواب خودمونی بده و برگرد به موضوع شکار",
                "confused": "کاربر گیج شده، ساده راهنمایی کن",
            }
            llm_out = _llm_chat(prompt_map.get(step, "سلام خودمونی بگو"))
            if llm_out and len(llm_out) > 10:
                return llm_out
        except Exception:
            pass

    if step == "greeting":
        return _pick(GREETINGS) + "\n\n" + _pick(ASK_PRODUCTS)
    if step == "ask_products":
        return _pick(ASK_PRODUCTS)
    if step == "ask_sell_price":
        model = context.get("model", "این دستگاه")
        return _pick(ASK_SELL_PRICE).format(model=model)
    if step == "ask_profit":
        model = context.get("model", "این دستگاه")
        sell = context.get("sell_price", 0)
        sell_s = f"{sell//1_000_000} میلیون" if sell else "?"
        try:
            return _pick(ASK_PROFIT).format(model=model, sell=sell_s)
        except:
            return _pick(ASK_PROFIT).format(model=model)
    if step == "ask_quantity":
        model = context.get("model", "این دستگاه")
        try:
            return _pick(ASK_QUANTITY).format(model=model)
        except:
            return _pick(ASK_QUANTITY)
    if step == "ask_conditions":
        return _pick(ASK_CONDITIONS)
    if step == "small_talk":
        return _pick(SMALL_TALK_REPLIES) + " " + generate_ai_message(context.get("next_step", "ask_products"), context)
    if step == "confused":
        return _pick(CONFUSED_REPLIES)
    if step == "confirm":
        prods = context.get("products", [])
        lines = [_pick(CONFIRM_TEMPLATES)]
        for p in prods:
            sp = p.get("sell_price", 0)
            pr = p.get("profit", 0)
            pr_pct = p.get("profit_percent", 0)
            qty = p.get("quantity", context.get("quantity", 1))
            sp_s = f"{sp//1_000_000} میلیون" if sp else "نامشخص"
            if pr_pct:
                pr_s = f"{pr_pct}%"
                if pr:
                    pr_s += f" (~{pr//1_000_000}م)"
            else:
                pr_s = f"{pr//1_000_000} میلیون" if pr and pr >= 1_000_000 else f"{pr}" if pr else "نامشخص"
            lines.append(f"• {p.get('model')}: فروش سالم ~{sp_s}، سود ~{pr_s}، تعداد {qty}")
        if context.get("conditions"):
            lines.append(f"\n🧹 شرایط: {', '.join(context.get('conditions',[]))}")
        if context.get("quantity"):
            lines.append(f"🔢 تعداد کل: {context.get('quantity')} تا هر مدل")
        lines.append("\nدرسته؟ اگه اوکیه بگو «اوکی» یا «حله» تا ست کنم، اگه چیزی جا مونده همینجوری بگو تا اضافه کنم 🙏")
        return "\n".join(lines)
    if step == "done":
        return _pick(FINAL_OK)
    return "بگو ببینم، دنبال چه دستگاهایی هستی؟ مثلا آیفون 12 13 14 15؟ 😎"


class HunterAIWizard:
    def __init__(self):
        self.reset()

    def reset(self):
        self.state: Dict[str, Any] = {
            "step": "greeting",
            "products": [],
            "current_idx": 0,
            "messages": [],
            "raw_goal": "",
            "done": False,
            "conditions": [],
            "quantity": 1,
        }

    def get_state(self) -> Dict[str, Any]:
        return dict(self.state)

    def set_state(self, s: Dict[str, Any]):
        self.state = dict(s)

    def _current_product(self) -> Optional[Dict[str, Any]]:
        idx = self.state.get("current_idx", 0)
        prods = self.state.get("products", [])
        if 0 <= idx < len(prods):
            return prods[idx]
        return None

    def start(self) -> Dict[str, Any]:
        self.reset()
        msg = generate_ai_message("greeting", {})
        self.state["messages"].append({"role": "assistant", "text": msg})
        return {
            "reply": msg,
            "messages": list(self.state["messages"]),
            "state": self.get_state(),
            "products": [],
            "config": self.build_config(),
            "ready": False,
            "done": False,
            "step": self.state["step"],
        }

    def _extract_and_store_global(self, user_text: str):
        """در هر پیام، تعداد و شرایط را حتی اگر در مرحله دیگری باشیم ذخیره کن."""
        q = extract_quantity(user_text)
        if q:
            self.state["quantity"] = q
            for p in self.state.get("products", []):
                if not p.get("quantity"):
                    p["quantity"] = q
        conds = extract_conditions(user_text)
        if conds:
            # ادغام بدون تکرار
            existing = self.state.get("conditions", [])
            for c in conds:
                if c not in existing:
                    existing.append(c)
            self.state["conditions"] = existing[:8]

    def handle_user(self, user_text: str) -> Dict[str, Any]:
        user_text = (user_text or "").strip()
        if not user_text:
            return {
                "reply": "یه چیزی بنویس تا بفهمم چی می‌خوای 😊 مثلا بگو «آیفون 12 13»",
                "messages": list(self.state["messages"]),
                "state": self.get_state(),
                "ready": False,
                "config": self.build_config(),
                "step": self.state.get("step"),
                "done": bool(self.state.get("done")),
                "products": self.state.get("products", []),
            }

        self.state["messages"].append({"role": "user", "text": user_text})
        step = self.state.get("step", "greeting")

        def _finalize(reply_text: str, ready=False, extra=None):
            self.state["messages"].append({"role": "assistant", "text": reply_text})
            out = {
                "reply": reply_text,
                "messages": list(self.state["messages"]),
                "state": self.get_state(),
                "products": self.state.get("products", []),
                "config": self.build_config(),
                "ready": ready or bool(self.state.get("done")),
                "done": bool(self.state.get("done")),
                "step": self.state.get("step", step),
            }
            if extra:
                out.update(extra)
            return out

        # --- همیشه تعداد و شرایط را بگیر (منعطف)
        self._extract_and_store_global(user_text)

        # --- تشخیص احوالپرسی و گیجی
        if is_greeting(user_text) and len(user_text) < 30 and not self.state["products"]:
            # اگر فقط سلام کرده
            reply = generate_ai_message("greeting", {"last_user": user_text})
            self.state["step"] = "ask_products"
            return _finalize(reply, ready=False)

        if is_greeting(user_text) and self.state["products"]:
            # سلام وسط کار
            reply = _pick(SMALL_TALK_REPLIES) + "\n\n" + generate_ai_message(step, {"model": self._current_product()["model"] if self._current_product() else "دستگاه", "last_user": user_text})
            return _finalize(reply, ready=False)

        if is_thanks(user_text) and len(user_text) < 25:
            reply = _pick(SMALL_TALK_REPLIES)
            # دوباره سوال فعلی را بپرس
            cur = self._current_product()
            if cur and step in ("ask_sell_price", "ask_profit", "ask_quantity", "ask_conditions", "confirm"):
                reply += "\n\n" + generate_ai_message(step, {"model": cur["model"], "sell_price": cur.get("sell_price", 0), "profit": cur.get("profit", 0)})
            return _finalize(reply, ready=False)

        if is_confused(user_text) and len(user_text) < 40:
            reply = generate_ai_message("confused", {"last_user": user_text})
            cur = self._current_product()
            if cur:
                reply += "\n\n" + generate_ai_message(step, {"model": cur["model"], "sell_price": cur.get("sell_price", 0)})
            return _finalize(reply, ready=False)

        # --- اگر هنوز محصول نداریم، استخراج کن
        if not self.state["products"]:
            prods = extract_products_from_text(user_text)
            if prods:
                self.state["products"] = prods
                self.state["raw_goal"] = user_text
                self.state["step"] = "ask_sell_price"
                self.state["current_idx"] = 0
                cur = self._current_product()
                reply = f"به به! {len(prods)} تا مدل گرفتم: {', '.join([p['model'] for p in prods])} 😍\n\n" + generate_ai_message(
                    "ask_sell_price", {"model": cur["model"] if cur else "این دستگاه", "last_user": user_text}
                )
                return _finalize(reply, ready=False)

        if step == "greeting" or step == "ask_products":
            prods = extract_products_from_text(user_text)
            if prods:
                existing = {p["model"] for p in self.state["products"]}
                added = []
                for p in prods:
                    if p["model"] not in existing:
                        self.state["products"].append(p)
                        added.append(p["model"])
                if added:
                    self.state["step"] = "ask_sell_price"
                    cur = self._current_product()
                    reply = f"عالیه! اضافه کردم: {', '.join(added)} ✅\n\n" + generate_ai_message(
                        "ask_sell_price", {"model": cur["model"] if cur else "دستگاه", "last_user": user_text}
                    )
                    return _finalize(reply, ready=False)
            if self.state["products"]:
                self.state["step"] = "ask_sell_price"
                cur = self._current_product()
                reply = generate_ai_message("ask_sell_price", {"model": cur["model"] if cur else "دستگاه", "last_user": user_text})
                return _finalize(reply, ready=False)
            else:
                reply = generate_ai_message("ask_products", {"last_user": user_text})
                return _finalize(reply, ready=False)

        if step == "ask_sell_price":
            cur = self._current_product()
            if cur:
                # اگر کاربر دو عدد داده: فروش و سود
                cands = parse_all_price_candidates(user_text, current_model=cur.get("model",""))
                # فیلتر فقط قیمت‌ها (نه درصد) و بزرگتر از 1م
                price_cands = [c for c in cands if not c[1] and c[0] >= 1_000_000]
                # حذف عدد مدل اگر به اشتباه به عنوان قیمت آمده و عدد دیگر هم هست
                # مثلا "13 25 فروش" -> 13 مدل است، 25 قیمت
                try:
                    model_nums = set()
                    for mm in re.finditer(r"([0-9]{1,2})", cur.get("model","")):
                        model_nums.add(int(mm.group(1))*1_000_000)
                    if len(price_cands) >= 2:
                        # اگر اولین کاندید مساوی عدد مدل است و دومی بزرگتر، اولی را حذف کن
                        if price_cands[0][0] in model_nums and price_cands[0][0] <= 16_000_000:
                            # چک کن آیا قیمت دوم منطقی‌تر است (بزرگتر از 16)
                            if price_cands[1][0] > price_cands[0][0]:
                                price_cands = price_cands[1:]
                except:
                    pass
                percent_cands = [c for c in cands if c[1]]

                # اگر درصد و قیمت با هم داده
                if price_cands:
                    # اولین قیمت = فروش
                    cur["sell_price"] = price_cands[0][0]
                    # اگر قیمت دوم هم هست، به عنوان سود بگیر
                    if len(price_cands) >= 2:
                        # دومین قیمت کوچکتر از اولی باشد معمولا سود است
                        if price_cands[1][0] < price_cands[0][0]:
                            cur["profit"] = price_cands[1][0]
                            # برو بعدی
                            idx = self.state["current_idx"]
                            if idx + 1 < len(self.state["products"]):
                                self.state["current_idx"] += 1
                                self.state["step"] = "ask_sell_price"
                                nxt = self._current_product()
                                reply = f"ایول! {cur['model']} فروش {price_cands[0][0]//1_000_000}م سود {price_cands[1][0]//1_000_000}م ثبت شد ✅ حالا بریم سراغ {nxt['model']}...\n\n" + generate_ai_message("ask_sell_price", {"model": nxt["model"]})
                                return _finalize(reply, ready=False)
                            else:
                                self.state["step"] = "ask_quantity" if not self.state.get("quantity") or self.state["quantity"] == 1 else "ask_conditions"
                                if self.state["step"] == "ask_quantity":
                                    reply = generate_ai_message("ask_quantity", {"model": cur["model"]})
                                else:
                                    reply = generate_ai_message("ask_conditions", {})
                                return _finalize(reply, ready=False)
                    if percent_cands:
                        cur["profit_percent"] = percent_cands[0][0]
                        cur["profit"] = int(cur["sell_price"] * percent_cands[0][0] / 100)
                        idx = self.state["current_idx"]
                        if idx + 1 < len(self.state["products"]):
                            self.state["current_idx"] += 1
                            self.state["step"] = "ask_sell_price"
                            nxt = self._current_product()
                            reply = f"دمت گرم! {cur['model']} فروش {cur['sell_price']//1_000_000}م سود {percent_cands[0][0]}% ثبت شد ✅ حالا {nxt['model']}...\n\n" + generate_ai_message("ask_sell_price", {"model": nxt["model"]})
                            return _finalize(reply, ready=False)
                        else:
                            self.state["step"] = "ask_profit" if not cur.get("profit") else ("ask_quantity" if not self.state.get("quantity") or self.state["quantity"]==1 else "ask_conditions")
                            # اگر سود را هم گرفتیم، برو مرحله بعد
                            if cur.get("profit"):
                                self.state["step"] = "ask_quantity" if not self.state.get("quantity") or self.state["quantity"]==1 else "ask_conditions"
                                if self.state["step"] == "ask_quantity":
                                    reply = generate_ai_message("ask_quantity", {"model": cur["model"]})
                                else:
                                    reply = generate_ai_message("ask_conditions", {})
                                return _finalize(reply, ready=False)

                    # فقط فروش داریم
                    self.state["step"] = "ask_profit"
                    reply = generate_ai_message("ask_profit", {"model": cur["model"], "sell_price": cur["sell_price"]})
                    return _finalize(reply, ready=False)
                else:
                    # شاید فقط درصد سود داده در مرحله قیمت؟ بگذار به سود برود
                    price = _parse_price_to_toman(user_text)
                    if price and price >= 1_000_000:
                        cur["sell_price"] = price
                        self.state["step"] = "ask_profit"
                        reply = generate_ai_message("ask_profit", {"model": cur["model"], "sell_price": price})
                        return _finalize(reply, ready=False)
                    # اگر عدد کوچک بدون میلیون مثل "20" بدهد
                    m = re.search(r"\b(\d{1,3})\b", user_text)
                    if m and "میلیون" not in user_text:
                        try:
                            v = int(m.group(1))
                            if 5 <= v <= 500:
                                cur["sell_price"] = v * 1_000_000
                                self.state["step"] = "ask_profit"
                                reply = generate_ai_message("ask_profit", {"model": cur["model"], "sell_price": cur["sell_price"]})
                                return _finalize(reply, ready=False)
                        except:
                            pass
                    reply = f"قیمت {cur['model']} رو دقیق متوجه نشدم داداش 😅 مثلا بگو «20 میلیون» یا «25m». چقدر می‌تونی سالم بفروشیش؟"
                    return _finalize(reply, ready=False)

        if step == "ask_profit":
            cur = self._current_product()
            if cur:
                cands = parse_all_price_candidates(user_text, current_model=cur.get("model",""))
                # اول درصد
                pct_cands = [c for c in cands if c[1]]
                price_cands = [c for c in cands if not c[1] and c[0] >= 500_000]

                if pct_cands:
                    pct = pct_cands[0][0]
                    cur["profit_percent"] = pct
                    sp = cur.get("sell_price") or 0
                    if sp:
                        cur["profit"] = int(sp * pct / 100)
                    # برو بعدی
                    idx = self.state["current_idx"]
                    if idx + 1 < len(self.state["products"]):
                        self.state["current_idx"] += 1
                        self.state["step"] = "ask_sell_price"
                        nxt = self._current_product()
                        reply = f"عالیه! {cur['model']} سود {pct}% ثبت شد ✅ حالا بریم {nxt['model']}...\n\n" + generate_ai_message("ask_sell_price", {"model": nxt["model"]})
                        return _finalize(reply, ready=False)
                    else:
                        self.state["step"] = "ask_quantity"
                        reply = generate_ai_message("ask_quantity", {"model": cur["model"]})
                        return _finalize(reply, ready=False)

                if price_cands:
                    # کوچکترین قیمت که کمتر از فروش باشد = سود
                    # اگر چندتا باشد، کوچکترین را سود بگیر
                    profit_val = None
                    sp = cur.get("sell_price") or 0
                    for val, _, _ in price_cands:
                        if sp and val < sp:
                            profit_val = val
                            break
                    if not profit_val:
                        profit_val = min(price_cands, key=lambda x: x[0])[0]
                        # اگر profit بزرگتر از sell باشد، احتمالا اشتباه است، ولی قبول کن
                    cur["profit"] = int(profit_val)
                    idx = self.state["current_idx"]
                    if idx + 1 < len(self.state["products"]):
                        self.state["current_idx"] += 1
                        self.state["step"] = "ask_sell_price"
                        nxt = self._current_product()
                        reply = f"ایول! {cur['model']} سود {profit_val//1_000_000}م ثبت شد ✅ حالا {nxt['model']}...\n\n" + generate_ai_message("ask_sell_price", {"model": nxt["model"]})
                        return _finalize(reply, ready=False)
                    else:
                        self.state["step"] = "ask_quantity"
                        reply = generate_ai_message("ask_quantity", {"model": cur["model"]})
                        return _finalize(reply, ready=False)

                # fallback: عدد تنها
                m = re.search(r"\b(\d{1,3})\b", user_text)
                if m:
                    try:
                        v = int(m.group(1))
                        if 1 <= v <= 90 and ("درصد" in user_text or "%" in user_text):
                            cur["profit_percent"] = v
                            sp = cur.get("sell_price") or 0
                            if sp:
                                cur["profit"] = int(sp * v / 100)
                            idx = self.state["current_idx"]
                            if idx + 1 < len(self.state["products"]):
                                self.state["current_idx"] += 1
                                self.state["step"] = "ask_sell_price"
                                nxt = self._current_product()
                                reply = f"سود {v}% برای {cur['model']} ثبت شد ✅ حالا {nxt['model']}...\n\n" + generate_ai_message("ask_sell_price", {"model": nxt["model"]})
                                return _finalize(reply, ready=False)
                            else:
                                self.state["step"] = "ask_quantity"
                                reply = generate_ai_message("ask_quantity", {"model": cur["model"]})
                                return _finalize(reply, ready=False)
                        elif 1 <= v <= 100:
                            # اگر درصد نیست، به عنوان میلیون
                            cur["profit"] = v * 1_000_000
                            idx = self.state["current_idx"]
                            if idx + 1 < len(self.state["products"]):
                                self.state["current_idx"] += 1
                                self.state["step"] = "ask_sell_price"
                                nxt = self._current_product()
                                reply = f"سود {v}م برای {cur['model']} ثبت شد ✅ حالا {nxt['model']}...\n\n" + generate_ai_message("ask_sell_price", {"model": nxt["model"]})
                                return _finalize(reply, ready=False)
                            else:
                                self.state["step"] = "ask_quantity"
                                reply = generate_ai_message("ask_quantity", {"model": cur["model"]})
                                return _finalize(reply, ready=False)
                    except:
                        pass

                reply = f"سود {cur['model']} رو دقیق نگرفتم عشقم 😅 مثلا بگو «3 میلیون» یا «10 درصد». چقدر سود می‌خوای؟"
                return _finalize(reply, ready=False)

        if step == "ask_quantity":
            q = extract_quantity(user_text)
            if q:
                self.state["quantity"] = q
                for p in self.state["products"]:
                    p["quantity"] = q
                self.state["step"] = "ask_conditions"
                reply = f"تعداد {q} تا ثبت شد ✅\n\n" + generate_ai_message("ask_conditions", {})
                return _finalize(reply, ready=False)
            else:
                m = re.search(r"\b(\d{1,3})\b", user_text)
                if m:
                    try:
                        v = int(m.group(1))
                        if 1 <= v <= 100:
                            self.state["quantity"] = v
                            for p in self.state["products"]:
                                p["quantity"] = v
                            self.state["step"] = "ask_conditions"
                            reply = f"تعداد {v} تا گرفتم ✅\n\n" + generate_ai_message("ask_conditions", {})
                            return _finalize(reply, ready=False)
                    except:
                        pass
                # اگر گفت هرچی بود
                if any(w in normalize(user_text) for w in ["هرچی", "مهم نیست", "فرقی نداره", "نامحدود"]):
                    self.state["quantity"] = 1
                    self.state["step"] = "ask_conditions"
                    reply = "باشه هرچی گیر اومد می‌گیریم 😎\n\n" + generate_ai_message("ask_conditions", {})
                    return _finalize(reply, ready=False)
                reply = "تعداد رو دقیق نگرفتم داداش 😅 مثلا بگو «5 تا» یا «هر مدل 3 تا». چند تا می‌خوای؟"
                return _finalize(reply, ready=False)

        if step == "ask_conditions":
            if any(w in normalize(user_text) for w in ["مهم نیست", "فرقی نداره", "هرچی", "نداره", "رد شو", "بیخیال"]):
                self.state["conditions"] = []
                self.state["step"] = "confirm"
                reply = generate_ai_message(
                    "confirm",
                    {
                        "products": self.state["products"],
                        "quantity": self.state["quantity"],
                        "conditions": self.state["conditions"],
                    },
                )
                return _finalize(reply, ready=False)
            conds = extract_conditions(user_text)
            # حتی اگر شرط خاصی نداشت، اگر متن کوتاه بود به عنوان شرط بگیر یا خالی بگذار و برو تایید
            if conds:
                # قبلا در _extract_and_store_global اضافه شده، ولی اینجا هم ست کن
                pass
            # اگر کاربر گفت "تمیز" یا یک کلمه
            if len(user_text) < 60 and "میلیون" not in user_text and "سود" not in user_text:
                # اگر قبلا شرایط داریم، برو تایید
                if self.state.get("conditions"):
                    self.state["step"] = "confirm"
                    reply = generate_ai_message(
                        "confirm",
                        {
                            "products": self.state["products"],
                            "quantity": self.state["quantity"],
                            "conditions": self.state["conditions"],
                        },
                    )
                    return _finalize(reply, ready=False)
                else:
                    # همین متن را شرط بگیر
                    if user_text not in self.state["conditions"]:
                        self.state["conditions"].append(user_text[:60])
                    self.state["step"] = "confirm"
                    reply = generate_ai_message(
                        "confirm",
                        {
                            "products": self.state["products"],
                            "quantity": self.state["quantity"],
                            "conditions": self.state["conditions"],
                        },
                    )
                    return _finalize(reply, ready=False)
            # در غیر این صورت هم برو تایید
            self.state["step"] = "confirm"
            reply = generate_ai_message(
                "confirm",
                {
                    "products": self.state["products"],
                    "quantity": self.state["quantity"],
                    "conditions": self.state["conditions"],
                },
            )
            return _finalize(reply, ready=False)

        if step == "confirm":
            if is_affirmative(user_text):
                self.state["step"] = "done"
                self.state["done"] = True
                reply = generate_ai_message("done", {"products": self.state["products"]})
                cfg = self.build_config()
                return _finalize(reply, ready=True, extra={"config": cfg})
            if is_negative(user_text):
                reply = "باشه صبر می‌کنم، چی رو اصلاح کنم؟ مدل؟ قیمت؟ سود؟ تعداد؟ بگو تا درست کنم 👇"
                return _finalize(reply, ready=False)
            # تلاش برای اصلاح
            new_prods = extract_products_from_text(user_text)
            if new_prods:
                existing = {p["model"] for p in self.state["products"]}
                added = []
                for p in new_prods:
                    if p["model"] not in existing:
                        self.state["products"].append(p)
                        added.append(p["model"])
                if added:
                    reply = f"اضافه کردم: {', '.join(added)} ✅ حالا باید قیمت فروش و سودشون رو هم بگی\n\n" + generate_ai_message(
                        "confirm",
                        {
                            "products": self.state["products"],
                            "quantity": self.state["quantity"],
                            "conditions": self.state["conditions"],
                        },
                    )
                    # اگر محصول جدید اضافه شد، باید قیمتش را بپرسیم
                    # برو به اولین محصول بدون قیمت
                    for idx, p in enumerate(self.state["products"]):
                        if not p.get("sell_price"):
                            self.state["current_idx"] = idx
                            self.state["step"] = "ask_sell_price"
                            reply = f"اضافه کردم {', '.join(added)} ✅ حالا قیمت فروش {p['model']} چنده؟\n\n" + generate_ai_message("ask_sell_price", {"model": p["model"]})
                            return _finalize(reply, ready=False)
                    return _finalize(reply, ready=False)
            q = extract_quantity(user_text)
            if q:
                self.state["quantity"] = q
                for p in self.state["products"]:
                    p["quantity"] = q
                reply = f"تعداد رو کردم {q} تا 👍\n\n" + generate_ai_message(
                    "confirm",
                    {
                        "products": self.state["products"],
                        "quantity": self.state["quantity"],
                        "conditions": self.state["conditions"],
                    },
                )
                return _finalize(reply, ready=False)
            conds = extract_conditions(user_text)
            if conds:
                self.state["conditions"] = conds
                reply = "شرایط اصلاح شد 👍\n\n" + generate_ai_message(
                    "confirm",
                    {
                        "products": self.state["products"],
                        "quantity": self.state["quantity"],
                        "conditions": self.state["conditions"],
                    },
                )
                return _finalize(reply, ready=False)
            cands = parse_all_price_candidates(user_text, current_model=self.state["products"][-1].get("model","") if self.state["products"] else "")
            if cands:
                # اگر کاربر در مرحله تایید قیمت جدید داده، آخرین محصول را اصلاح کن
                cur = self.state["products"][-1] if self.state["products"] else None
                if cur:
                    price_cands = [c for c in cands if not c[1]]
                    pct_cands = [c for c in cands if c[1]]
                    if price_cands:
                        # اگر یک قیمت داده، ببین فروش دارد یا نه
                        if not cur.get("sell_price"):
                            cur["sell_price"] = price_cands[0][0]
                        elif not cur.get("profit"):
                            cur["profit"] = price_cands[0][0]
                        else:
                            cur["sell_price"] = price_cands[0][0]
                    if pct_cands:
                        cur["profit_percent"] = pct_cands[0][0]
                        if cur.get("sell_price"):
                            cur["profit"] = int(cur["sell_price"] * pct_cands[0][0] / 100)
                    reply = "اوکی، اصلاح شد 👍\n\n" + generate_ai_message(
                        "confirm",
                        {
                            "products": self.state["products"],
                            "quantity": self.state["quantity"],
                            "conditions": self.state["conditions"],
                        },
                    )
                    return _finalize(reply, ready=False)
            reply = generate_ai_message(
                "confirm",
                {
                    "products": self.state["products"],
                    "quantity": self.state["quantity"],
                    "conditions": self.state["conditions"],
                },
            )
            return _finalize(reply, ready=False)

        if step == "done":
            if is_affirmative(user_text) or "ست" in normalize(user_text):
                cfg = self.build_config()
                reply = generate_ai_message("done", {"products": self.state["products"]})
                return _finalize(reply, ready=True, extra={"config": cfg})
            # اگر چیز جدیدی گفت، ریست نکن، بلکه بگو آماده است
            cfg = self.build_config()
            reply = generate_ai_message("done", {"products": self.state["products"]})
            return _finalize(reply, ready=True, extra={"config": cfg})

        reply = "بگو ببینم، دنبال چه دستگاهایی هستی؟ مثلا آیفون 12 13 14 15؟ 😎"
        return _finalize(reply, ready=False)

    def build_config(self) -> Dict[str, Any]:
        keywords = []
        hunter_adv_by_keyword = {}
        warnings = []
        for p in self.state["products"]:
            model = p.get("model") or p.get("keyword") or "دستگاه"
            sell_price = int(p.get("sell_price") or 0)
            profit = int(p.get("profit") or 0)
            profit_percent = float(p.get("profit_percent") or 0)
            if profit_percent and not profit:
                if sell_price:
                    profit = int(sell_price * profit_percent / 100)
            buy_target = sell_price - profit if sell_price and profit else 0
            if buy_target <= 0 and sell_price:
                buy_target = int(sell_price * 0.85)
            if sell_price and profit:
                pct = profit / sell_price * 100
                good_pct = max(8, min(25, pct * 0.8))
                great_pct = max(12, min(35, pct * 1.2))
            else:
                good_pct = 10
                great_pct = 20
            adv = {
                "good_pct": round(good_pct, 1),
                "great_pct": round(great_pct, 1),
                "suspicious_pct": 50,
                "dealer_mode": False,
                "sell_price": sell_price,
                "profit": profit,
                "profit_percent": profit_percent,
                "buy_target": buy_target,
                "quantity": p.get("quantity", self.state.get("quantity", 1)),
                "model": model,
                "conditions": self.state.get("conditions", []),
            }
            price_min = int(buy_target * 0.5) if buy_target else 0
            price_max = int(buy_target * 1.1) if buy_target else 0
            keywords.append(
                {
                    "keyword": model,
                    "category": p.get("category") or "mobile-phones",
                    "price_min": price_min,
                    "price_max": price_max,
                    "hunter": True,
                    "vip": True,
                    "hunter_adv": adv,
                    "sell_price": sell_price,
                    "profit": profit,
                    "buy_target": buy_target,
                }
            )
            hunter_adv_by_keyword[model] = adv
            if sell_price and profit and profit > sell_price * 0.3:
                warnings.append(f"{model}: سود {profit//1_000_000}م روی فروش {sell_price//1_000_000}م خیلی بالاست")

        items = []
        for k in keywords:
            items.append(
                {
                    "model": k["keyword"],
                    "keyword": k["keyword"],
                    "category": k["category"],
                    "healthy_sell_price": k["sell_price"],
                    "desired_profit": k["profit"],
                    "max_buy": k["buy_target"],
                    "price_min": k["price_min"],
                    "price_max": k["price_max"],
                    "hunter_adv": k["hunter_adv"],
                    "conditions": self.state.get("conditions", []),
                    "quantity": k["hunter_adv"].get("quantity", 1),
                }
            )

        return {
            "products": self.state["products"],
            "keywords": keywords,
            "items": items,
            "hunter_adv": hunter_adv_by_keyword,
            "warnings": warnings,
            "summary": f"{len(keywords)} مدل تنظیم شد — سود متوسط {(sum(k['profit'] for k in keywords)//len(keywords)//1_000_000) if keywords else 0} میلیون"
            if keywords
            else "هنوز مدلی ثبت نشده",
            "created_at": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
            "state": self.state.get("step"),
            "quantity": self.state.get("quantity", 1),
            "conditions": self.state.get("conditions", []),
        }


_wizard_sessions: Dict[str, HunterAIWizard] = {}

def get_wizard(session_id: str) -> HunterAIWizard:
    if session_id not in _wizard_sessions:
        _wizard_sessions[session_id] = HunterAIWizard()
    return _wizard_sessions[session_id]
