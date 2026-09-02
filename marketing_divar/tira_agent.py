# -*- coding: utf-8 -*-
"""تیرا — ایجنت تمام‌عیار شکارچی

این ماژول قلب هوشمندی v3.6 است:
- تسلط کامل به پنل SMS، تنظیمات، پلتفرم‌ها، اینترنت واقعی
- تحقیق بازار ایران برای هر کالا (موبایل مثال بود، ولی هر کالایی را می‌فهمد)
- برای آیفون 13/14/15 و واریانت‌های عادی/پرو/پرومکس/مینی/پلاس/نات‌اکتیو قیمت جدا می‌گیرد
- درصد افت باتری/رجیستر/خش/تعمیر و هزاران پارامتر را می‌داند
- تعاملی پارامترهای شکار را جمع می‌کند، تنظیمات پیشرفته می‌سازد، موتور شکار را روشن می‌کند
- پیامک/چت دیوار+شیپور می‌فرستد، پاسخ با سیم دوم را تشخیص می‌دهد، مذاکره انسانی مودب (نه ربات‌وار)

استفاده:
  from .tira_agent import get_tira_agent
  agent = get_tira_agent(session_id)
  agent.handle_user("سری 13 14 15 شکار کن")
"""

from __future__ import annotations

import re
import time
import random
from typing import Any, Dict, List, Optional, Tuple

try:
    from .market_research import (
        research_product,
        get_all_iphone_series_from_text,
        get_iphone_variants,
        PRICE_FACTORS_IPHONE,
        build_hunter_adv_from_research,
        IPHONE_VARIANTS,
    )
except Exception:
    # fallback اگر import نشد
    def research_product(kw):  # type: ignore
        return {"product": kw, "type": "generic", "variants": [kw], "factors": [], "market_note": ""}
    def get_all_iphone_series_from_text(t):  # type: ignore
        return []
    def get_iphone_variants(s):  # type: ignore
        return [f"آیفون {s}"]
    PRICE_FACTORS_IPHONE = []  # type: ignore
    def build_hunter_adv_from_research(r, sp, pp):  # type: ignore
        return {}
    IPHONE_VARIANTS = {}

try:
    from .price_knowledge import fetch_market_price_from_web, get_dynamic_adjustments_for_product
except Exception:
    def fetch_market_price_from_web(prod, timeout=8, use_cache=True):  # type: ignore
        return None
    def get_dynamic_adjustments_for_product(kw):  # type: ignore
        return {}

try:
    from .profitability import calculate_profitability, test_and_improve_profitability
except Exception:
    def calculate_profitability(title, market_price_new=None, sell_price_healthy=None, desired_profit_pct=10, desired_profit_toman=None, conditions_text="", extra_factors=None, db_path="data/divar_leads.db"):
        return {}
    def test_and_improve_profitability(title, iterations=3):
        return {}

try:
    from .hunter_ai_wizard import (
        get_market_price_for_model,
        extract_products_from_text,
        _parse_price_to_toman,
        parse_all_price_candidates,
    )
except Exception:
    def get_market_price_for_model(m):  # type: ignore
        return None
    def extract_products_from_text(t):  # type: ignore
        return []
    def _parse_price_to_toman(t):  # type: ignore
        return None
    def parse_all_price_candidates(t, current_model=""):  # type: ignore
        return []

# ------------------------------------------------ دانش سیستم — راهنماها
SYSTEM_GUIDES = {
    "sms": """
📱 **راهنمای کامل پنل پیامکی ملی‌پیامک — چطور پیامک بره؟**

**مرحله 1 — ساخت حساب ملی‌پیامک:**
1. برو به https://www.melipayamak.com → ثبت‌نام
2. بعد از تایید، وارد پنل شو: https://console.melipayamak.com
3. از منو: **تنظیمات → اطلاعات حساب** → نام کاربری و رمز API را بردار
4. یک خط اختصاصی بخر (مثلاً 5000... یا 3000...) — یا از خط خدماتی با پترن استفاده کن

**مرحله 2 — تنظیم در برنامه ما:**
- تب **تنظیمات → 📱 ملی‌پیامک**
- سرویس‌دهنده: ملی‌پیامک
- نام کاربری: همون نام کاربری پنل ملی‌پیامک
- رمز عبور: رمز API (یا رمز اصلی)
- روش ارسال:
  • **خط اختصاصی**: شماره خط خودت رو بگذار (مثلاً 500012345)
  • **پترن (خط خدماتی)**: کد پترن تأییدشده + متن پترن با متغیر {title} {city}
- سقف روزانه: مثلاً 100
- تیک **ارسال خودکار به محض پیدا شدن شماره** را روشن کن

**مرحله 3 — تست:**
- در همون بخش، شماره تست خودت (09...) را بزن و **ارسال آزمایشی** بزن
- اگر موجودی برگشت یا پیامک رسید، یعنی وصله
- دکمه **📊 بررسی تحویل** برای چک کردن تحویل پیامک‌های قبلی

**نکته‌ها:**
- اگر خط خدماتی داری، حتماً پترن را در پنل ملی‌پیامک ثبت و تأیید کن، وگرنه رد می‌شود
- متن پترن نباید لینک داشته باشد (divar.ir ننویس)
- اگر خط اختصاصی داری، ساده‌ترین حالت است — فقط خط را بگذار
- برنامه به محض پیدا شدن شماره، خودکار همین متن را می‌فرستد اگر تیک خودکار روشن باشد

**عیب‌یابی:**
- «نام کاربری/رمز اشتباه»: دوباره از پنل ملی‌پیامک کپی کن
- «خط ارسال خالی»: شماره خط را وارد کن
- «پترن رد شد»: متن پترن را طبق نمونه برنامه بساز و در ملی‌پیامک ثبت کن
""",
    "internet": """
🌐 **اتصال تیرا به اینترنت — تحقیق بازار واقعی**

تیرا برای قیمت روز از **Torob API** + کش محلی استفاده می‌کند:

- مسیر: `marketing_divar/price_knowledge.py` → `fetch_market_price_from_web()`
- کش: `data/price_knowledge_cache.json` — 24 ساعت اعتبار
- اگر اینترنت نباشد، خودکار fallback به میانه آگهی‌های همان دسته

**برای هر کالا (نه فقط موبایل):**
- تیرا اول نوع کالا را تشخیص می‌دهد (موبایل، خودرو، لپ‌تاپ، لوازم خانگی، ...)
- واریانت‌ها را از دانش `market_research.py` می‌گیرد (مثلاً آیفون 13 → عادی/مینی/پرو/پرومکس/نات‌اکتیو)
- عوامل افت قیمت را جدا می‌داند: باتری زیر 80٪ -11٪، بدون رجیستر -16٪، تعمیر -14٪، نات‌اکتیو -6٪ (ریسک فیک، با فاکتور +3٪)، با کارتن +3٪ و ...
- قیمت نو را از ترب می‌گیرد، دست دوم سالم را 15-25٪ زیر نو حساب می‌کند

**تست قیمت:**
- تب تیرا بگو «قیمت آیفون 13 پرو مکس نات‌اکتیو چنده؟»
- یا GET /api/tira/price?query=آیفون 13 پرو مکس نات اکتیو

**اگر اینترنت نداری:**
- برنامه بدون اینترنت هم کار می‌کند — فقط قیمت ترب نمی‌آید، ولی شکارچی با میانه آگهی‌های دیوار کار می‌کند
- برای تست آفلاین، کش قبلی استفاده می‌شود
""",
    "platforms": """
👤 **اکانت‌ها — دیوار + شیپور کامل**

**هر شماره دو لاگین جدا:**
- دکمه «📱 ارسال کد دیوار»: کد دیوار via API رسمی می‌فرستد، کد را وارد و تأیید کن
- دکمه «🏪 ارسال کد شیپور»: چون شیپور OTP رسمی ندارد، پروفایل Chromium باز می‌شود روی sheypoor.com/session — همانجا شماره و کد را بزن

**ساخت پروفایل:**
- دکمه «➕ ایجاد پروفایل (دیوار+شیپور)»: یک پروفایل Chromium جدا با نام همین اکانت می‌سازد (accounts/نام/chromium)
- Chromium اختصاصی برنامه باز می‌شود با دو تب: تب اول divar.ir/user، تب دوم sheypoor.com/session
- در هر تب لاگین کن، بعد در لیست اکانت‌ها «💾 ذخیره پروفایل» را بزن — پنجره بسته می‌شود و لاگین می‌ماند

**بعد از ذخیره:**
- فقط دو دکمه می‌ماند: «🌐 باز کردن دیوار»، «🏪 باز کردن شیپور» + «🗑️ حذف کامل اکانت»
- کنار هر اکانت آیکون دیوار و شیپور با toggle روشن/خاموش است — می‌توانی شیپور را خاموش کنی یا دیوار را خاموش کنی، موتور فقط روی پلتفرم‌های روشن کار می‌کند

**شیپور جستجو و شماره‌گیری:**
- مثل دیوار کامل شد: جستجو via Chromium، شماره‌گیری via همان پروفایل
- اگر لاگین شیپور دیده نشد، پروفایل را باز کن و دوباره لاگین کن

**کپچا:**
- تشخیص دقیق: فقط وقتی واقعاً پازل arkose/hcaptcha/recaptcha یا 403 با marker کپچا بیاید، اکانت کپچا می‌شود
- خطای ساده «شماره در صفحه نبود» دیگر کپچا حساب نمی‌شود
""",
    "hunter": """
🎯 **شکارچی هوشمند — چطور کار می‌کند؟**

**هدف:** وقتی می‌گی «سری 13 14 15 شکار کن»، تیرا واریانت‌ها را جدا تحقیق می‌کند.

**مرحله 1 — تحقیق:**
- از market_research.py می‌فهمد آیفون 13 چه واریانت‌هایی دارد: عادی، مینی، پرو، پرو مکس، نات‌اکتیو
- برای هر واریانت قیمت نو از ترب می‌گیرد
- عوامل افت را می‌داند: باتری، رجیستر، خش، تعمیر، فیس‌آیدی، کارتن...

**مرحله 2 — سوال تعاملی از تو:**
- منظورت کدوم واریانت‌هاست؟ هر سه تا یا فقط پرومکس؟
- نو می‌خوای یا دست دوم؟
- قیمت فروش سالم هر مدل چنده؟ (مثلاً آیفون 13 سالم 25 میلیون)
- چقدر سود می‌خوای؟ درصدی یا تومانی؟ (مثلاً 10٪ یا 3 میلیون)
- شرایط: خش، باتری، رجیستر و ... — هزاران پارامتر

**مرحله 3 — ساخت تنظیمات پیشرفته:**
- با تایید تو، تنظیمات با صدها پارامتر می‌سازد: good_pct، great_pct، suspicious_pct، adjustments برای هر عامل افت
- مثلاً اگر باتری زیر 80٪ -11٪، بدون رجیستر -16٪، تعمیر -14٪، نات‌اکتیو -6٪ (ریسک فیک، با فاکتور +3٪)
- قیمت فروش منهای سود = حد خرید، بعد فیلتر شکارچی

**مرحله 4 — موتور شکار:**
- مانیتور دیوار+شیپور را می‌گردد، توضیحات آگهی را می‌خواند، قیمت را چک می‌کند
- اگر شکار بود، پیامک/چت می‌فرستد (قالب با کمک تیرا)
- منتظر پاسخ می‌ماند — اگر با سیم دوم جواب داد، تشخیص می‌دهد و می‌پرسد «شما مربوط به کدوم آگهیه؟»
- مذاکره انسانی مودب، نه ربات‌وار، با احترام قشنگ

**مرحله 5 — تست:**
- تب تنظیمات → 🧪 تست تیرا: شماره خودت را بده، تیرا فکر می‌کند یک آگهی پیدا کرده و با تو مذاکره می‌کند
- حتی می‌تونی با شماره دوم پیام بدی، ببینی درست تطبیق می‌دهد
""",
    "general": """
🧠 **تیرا — دستیار شکار حرفه‌ای (ایجنت کامل)**

تیرا به همه جای برنامه مسلطه:

- **پنل SMS:** توضیح بالا
- **تنظیمات:** watch_interval، phone_delay، per_account_daily، ip_daily_limit، cooldown، adaptive_until_captcha
- **پلتفرم‌ها:** دیوار، شیپور — هر کدوم جدا خاموش/روشن
- **کلمات کلیدی:** دسته‌بندی بدون املاک، شهرها آبشاری کشویی با تیک، حداقل/حداکثر قیمت، شکارچی
- **قالب پیام‌ها:** چت، پیامک، استعلام — با متغیر {title} {city} {price} — تیرا متن حرفه‌ای می‌نویسد
- **صندوق پیام‌ها:** دریافت/ارسال اتومات، مذاکره تیرا، پاسخ‌ها، شکارهای VIP، هفته گذشته
- **سرنخ‌ها:** لیست همه، شماره‌دار، فقط چت، شکارچی، پاسخ‌ها
- **اینترنت:** قیمت روز از ترب، تحقیق بازار ایران 1403

هر سوالی داری، همینجا از تیرا بپرس — مثلاً «چطور پنل پیامکی رو تنظیم کنم؟» یا «قیمت آیفون 15 پرو نات‌اکتیو چنده؟» یا «برای آیفون 13 14 15 شکار بساز»
""",
}

# عوامل عمومی برای کالاهای غیر موبایل
GENERIC_FACTORS = [
    {"key": "used", "label": "کارکرده", "pct": -15, "words": ["کارکرده", "دست دوم"], "question": "نو یا کارکرده؟", "research": "کارکرده معمولاً 10-20٪ زیر نو"},
    {"key": "scratch", "label": "خط و خش", "pct": -7, "words": ["خش", "خط"], "question": "خط و خش داره؟", "research": "خش 5-10٪ افت"},
    {"key": "repaired", "label": "تعمیر شده", "pct": -12, "words": ["تعمیر", "تعویض"], "question": "تعمیر شده؟", "research": "تعمیر 10-15٪ افت"},
    {"key": "with_box", "label": "با کارتن و لوازم", "pct": +4, "words": ["کارتن", "لوازم کامل"], "question": "کارتن داره؟", "research": "با کارتن 3-5٪ گران‌تر"},
    {"key": "not_active", "label": "نات‌اکتیو / پلمپ (ریسک فیک - تحقیق اینترنت)", "pct": -6, "words": ["نات اکتیو", "پلمپ", "آکبند"], "question": "نات‌اکتیو با فاکتور معتبر یا فقط ادعایی؟", "research": "بازار ایران 1403: ادعای نات‌اکتیو بدون فاکتور 5-8٪ افت ریسک دارد (فیک زیاد)، با فاکتور +3٪. درصد از اینترنت (ترب) به‌روز می‌شود نه هاردکد", "dynamic": True, "source": "internet_research"},
]

def get_system_guide(topic: str = "general") -> str:
    t = (topic or "general").lower()
    if "sms" in t or "پیامک" in t or "ملی" in t:
        return SYSTEM_GUIDES["sms"]
    if "اینترنت" in t or "price" in t or "ترب" in t or "قیمت" in t:
        return SYSTEM_GUIDES["internet"]
    if "پلتفرم" in t or "اکانت" in t or "دیوار" in t or "شیپور" in t:
        return SYSTEM_GUIDES["platforms"]
    if "شکار" in t or "hunter" in t:
        return SYSTEM_GUIDES["hunter"]
    return SYSTEM_GUIDES["general"] + "\n\n" + SYSTEM_GUIDES["sms"] + "\n\n" + SYSTEM_GUIDES["hunter"]

def research_any_product(keyword: str) -> Dict[str, Any]:
    """تحقیق برای هر کالا — موبایل مثال بود، ولی هر کالایی را می‌فهمد"""
    kw = (keyword or "").strip()
    if not kw:
        return {"product": "", "variants": [], "factors": GENERIC_FACTORS, "market_note": "", "prices": []}

    # اول از market_research استفاده کن (آیفون و ...)
    res = research_product(kw)

    # قیمت‌ها را از اینترنت بگیر
    prices = []
    try:
        # اگر واریانت دارد، هر کدام را جدا قیمت بگیر
        variants = res.get("variants") or [kw]
        for var in variants[:12]:  # حداکثر 12 تا برای سرعت
            try:
                p = get_market_price_for_model(var)
                if p:
                    prices.append({"model": var, "price": int(p), "price_million": int(p)//1_000_000, "source": "torob", "has_price": True})
                else:
                    # تلاش مستقیم via price_knowledge
                    prod = {"keyword": var, "model": var}
                    pp = fetch_market_price_from_web(prod, timeout=5)
                    if pp:
                        prices.append({"model": var, "price": int(pp), "price_million": int(pp)//1_000_000, "source": "web", "has_price": True})
            except Exception:
                continue
        # اگر هیچ قیمتی پیدا نشد، خود keyword را امتحان کن
        if not prices:
            try:
                prod = {"keyword": kw, "model": kw}
                pp = fetch_market_price_from_web(prod, timeout=5)
                if pp:
                    prices.append({"model": kw, "price": int(pp), "price_million": int(pp)//1_000_000, "source": "web", "has_price": True})
            except Exception:
                pass
    except Exception:
        pass

    # اگر آیفون است، market_note دقیق‌تر
    if res.get("type") == "iphone":
        factors = res.get("factors") or PRICE_FACTORS_IPHONE
    else:
        # برای کالای عمومی، عوامل را بر اساس دسته حدس بزن — جاروبرقی لوازم خانگی است نه آیفون
        low = kw.lower()
        nkw = kw
        if any(x in low or x in nkw for x in ["پراید", "پژو", "سمند", "دنا", "تیبا", "خودرو", "ماشین", "car"]):
            try:
                from .market_research import PRICE_FACTORS_CAR
                factors = PRICE_FACTORS_CAR
            except Exception:
                factors = GENERIC_FACTORS
        elif any(x in nkw for x in ["جاروبرقی", "لباسشویی", "یخچال", "فریزر", "کولر", "اسپلیت"]):
            try:
                from .market_research import PRICE_FACTORS_APPLIANCE
                factors = PRICE_FACTORS_APPLIANCE
            except Exception:
                factors = GENERIC_FACTORS
        else:
            factors = res.get("factors") or GENERIC_FACTORS

    # محاسبه سودآوری با هزاران پارامتر — خودش تحقیق اینترنتی می‌کند و بر اساس پارامتر دوباره تنظیم می‌کند
    profitability = None
    try:
        profitability = calculate_profitability(kw, market_price_new=(prices[0]["price"] if prices else None), desired_profit_pct=10, conditions_text=kw)
    except Exception:
        profitability = None

    return {
        "product": kw,
        "type": res.get("type", "generic"),
        "series": res.get("series", []),
        "variants": res.get("variants") or [kw],
        "factors": factors,
        "market_note": res.get("market_note", "قیمت بر اساس میانه آگهی‌های همان دسته + افت وضعیت"),
        "prices": prices,
        "has_variants": res.get("has_variants", False),
        "profitability": profitability,
    }

def generate_polite_negotiation(context: Dict[str, Any], stage: str = "opener", history: Optional[List[Dict]] = None) -> str:
    """مذاکره انسانی مودب و حرفه‌ای — نه ربات‌وار، با درک منطق بازار ایران 1403
    - هر دستگاه اینترنت تحقیق می‌شود و ثبت می‌شود نه هاردکد
    - نات‌اکتیو -6% ریسک فیک (با فاکتور +3%) از تحقیق اینترنت
    - باتری، رجیستر، خش، تعمیر و هزاران پارامتر پویا
    - تاریخچه مذاکره را می‌بیند و تکراری نمی‌گوید
    """
    title = (context.get("title") or context.get("model") or "آگهی شما")[:70]
    price = context.get("price") or 0
    fair = context.get("fair") or context.get("healthy_median") or int(price * 1.15) if price else 0
    discount = context.get("discount_pct") or 0
    flags = context.get("flags") or {}
    missing = context.get("missing") or []
    factors = context.get("factors") or []
    variant_info = context.get("variant_info") or {}
    history = history or []

    def fmt(p):
        if not p:
            return "—"
        if p >= 1_000_000:
            m = int(p)//1_000_000
            # اگر اعشاری
            if p % 1_000_000 >= 100_000:
                return f"{p/1_000_000:.1f} میلیون"
            return f"{m} میلیون"
        return f"{p:,} تومان"

    def fmt_short(p):
        if not p:
            return ""
        return f"{int(p)//1_000_000}م"

    # تشخیص نوع کالا برای لحن
    low_title = title.lower()
    is_iphone = "آیفون" in title or "iphone" in low_title
    is_car = any(w in low_title for w in ["پراید", "پژو", "سمند", "خودرو", "ماشین"])

    # لحن‌های مودب انسانی — تنوع زیاد، نه تکراری
    greetings = [
        "سلام وقت بخیر",
        "سلام بزرگوار وقتتون بخیر",
        "درود وقت بخیر",
        "سلام خسته نباشید",
        "سلام عزیز وقت بخیر",
        "سلام قربان وقت بخیر",
    ]
    closings = [
        "ممنون از لطفتون",
        "سپاس از وقتی که می‌گذارید",
        "ممنون می‌شم راهنمایی کنید",
        "لطف می‌کنید",
        "ممنون از صبر و حوصله‌تون",
        "سپاسگزارم",
    ]
    # ایموجی‌های ملایم
    emojis = ["🙏", "🌹", "✨", ""]

    greet = random.choice(greetings)
    close = random.choice(closings)
    emoji = random.choice(emojis)

    # تاریخچه را چک کن تا تکراری نگویی
    prev_texts = " ".join([h.get("text","") for h in history[-4:]]).lower()

    if stage == "opener":
        # استعلام اولیه — هوشمند بر اساس جای خالی و پرچم‌ها
        if missing:
            # فقط 2 سوال اول، با لحن مودب
            qs = []
            for m in missing[:2]:
                f = next((x for x in factors if x.get("key")==m), None)
                q = f.get("question") if f else m
                # سوال را انسانی کن
                if "باتری" in q:
                    qs.append("باتری چند درصده؟")
                elif "رجیستر" in q:
                    qs.append("رجیستر شده؟")
                elif "خش" in q:
                    qs.append("بدنه خط و خش داره؟")
                elif "تعمیر" in q:
                    qs.append("تعمیر یا تعویض شده؟")
                elif "کارتن" in q:
                    qs.append("کارتن و لوازم داره؟")
                else:
                    qs.append(q)
            qtxt = " و ".join(qs)
            templates = [
                f"{greet}\nبرای آگهی «{title}» مزاحم شدم، می‌خواستم بپرسم {qtxt}؟ {close} {emoji}",
                f"{greet} بزرگوار\nآگهی «{title}» رو دیدم، لطف می‌کنید بفرمایید {qtxt}؟ {close}",
                f"{greet}\nببخشید برای «{title}» پیام دادم — {qtxt}؟ ممنون می‌شم بفرمایید {emoji}",
            ]
            return random.choice(templates)

        # اگر پرچم‌های منفی دارد (معیوب، بدون رجیستر...)
        if flags:
            neg_flags = [k for k,v in flags.items() if v]
            if "not_registered" in neg_flags:
                return f"{greet}\nبرای «{title}» پیام دادم. رجیسترش اوکیه؟ چون بدون رجیستر هزینه داره. قیمتتون {fmt(price)} هست، اگر رجیستر شده باشه می‌تونیم صحبت کنیم. {close} {emoji}"
            if "battery_low" in neg_flags:
                return f"{greet}\nبرای «{title}» مزاحم شدم. باتریش چنده؟ قیمت {fmt(price)} رو دیدم، اگر باتری بالای 85 باشه اوکیه. {close}"
            if "repaired" in neg_flags:
                return f"{greet}\nبرای «{title}» پیام دادم. تعمیر یا تعویض نداشته؟ قیمتتون رو دیدم. {close} {emoji}"

        # اگر شکار عالی است
        if discount and discount >= 10:
            # تحقیق اینترنت برای قیمت منصفانه
            market_note = ""
            if fair:
                market_note = f"من چند مورد مشابه دیدم حدود {fmt(fair)} بودن"
            templates = [
                f"{greet}\nبرای «{title}» پیام دادم. قیمتتون {fmt(price)} هست، {market_note}. آیا قیمتتون جای تخفیف داره؟ {close} {emoji}",
                f"{greet} بزرگوار\nآگهی «{title}» با قیمت {fmt(price)} رو دیدم. راستش بودجه من کمی پایین‌تره، {market_note} — امکان تخفیف هست؟ {close}",
                f"{greet}\nببخشید برای «{title}» مزاحم شدم. قیمت {fmt(price)} رو گذاشتید، {market_note}. اگر مقدور باشه با تخفیف صحبت کنیم ممنون می‌شم {emoji}",
            ]
            return random.choice(templates)

        # حالت عادی
        templates = [
            f"{greet}\nبرای آگهی «{title}» مزاحم شدم. می‌شه لطفاً جزئیات بیشتری بفرمایید؟ وضعیت، کارکرد، لوازم؟ {close} {emoji}",
            f"{greet} بزرگوار\n«{title}» رو دیدم، خیلی تمیز به نظر میاد. می‌شه بیشتر توضیح بدید؟ {close}",
            f"{greet}\nبرای «{title}» پیام دادم. هنوز موجوده؟ {close} {emoji}",
        ]
        return random.choice(templates)

    elif stage == "offer":
        # پیشنهاد قیمت — مودب، با دلیل، نقد
        target = context.get("target_price") or int(price * 0.92) if price else fair
        if not target and fair:
            target = int(fair * 0.95)
        if not target:
            target = int(price * 0.90) if price else 0

        # اگر باتری یا رجیستر مشکل دارد، دلیل بیار
        reason = ""
        if flags.get("battery_low"):
            reason = "با توجه به باتری"
        elif flags.get("not_registered"):
            reason = "با توجه به هزینه رجیستر"
        elif flags.get("scratch"):
            reason = "با توجه به خط و خش"
        elif variant_info.get("not_active") and not variant_info.get("with_receipt"):
            reason = "با توجه به ریسک نات‌اکتیو بدون فاکتور (بازار 5-8٪ افت)"

        templates = [
            f"{greet}\nممنون بابت توضیحات کامل. راستش بودجه من حدود {fmt(target)} هست و نقد آماده‌ام {reason}. اگر براتون مقدوره با این مبلغ معامله کنیم، امروز می‌تونم اقدام کنم. {close} {emoji}",
            f"{greet} بزرگوار\nلطف کردید توضیح دادید. من نقداً تا {fmt(target)} می‌تونم اقدام کنم {reason}. اگر اوکیه بفرمایید هماهنگ کنیم. {close}",
            f"{greet}\nخیلی ممنون. با توجه به شرایط بازار، من تا {fmt(target)} نقد آماده‌ام {reason}. اگر موافقید امروز معامله کنیم. {close} {emoji}",
            f"{greet}\nسپاس از توضیحات. بودجه من حدود {fmt(target)} نقد هست. اگر براتون مقدوره با این قیمت ببندیم، ممنون می‌شم {emoji}",
        ]
        # اگر قبلاً همین پیشنهاد را دادی، کمی متفاوت بگو
        if fmt_short(target) in prev_texts:
            templates = [t.replace(fmt(target), fmt(int(target*0.98))) for t in templates]
        return random.choice(templates)

    else:  # final / closer
        target = context.get("target_price") or int(price * 0.90) if price else fair
        if not target and fair:
            target = int(fair * 0.92)

        templates = [
            f"{greet}\nخیلی ممنون از وقتی که گذاشتید. من می‌تونم تا {fmt(target)} نقد همین امروز اقدام کنم. اگر موافقید بفرمایید تا هماهنگ کنیم. {close} {emoji} 🌹",
            f"{greet} بزرگوار\nجمع‌بندی کنم: من تا {fmt(target)} نقد آماده‌ام و امروز می‌تونم بیام. اگر با این مبلغ اوکیه، لطفاً خبر بدید تا نهایی کنیم. {close} {emoji}",
            f"{greet}\nممنون از صبرتون. آخرین پیشنهاد من {fmt(target)} نقد امروز هست. اگر مقدور بود ممنون می‌شم اطلاع بدید. {close} 🌹",
            f"{greet}\nبزرگوار، با احترام، من تا {fmt(target)} می‌تونم نقداً اقدام کنم. اگر براتون مقدوره، امروز معامله رو ببندیم. {close} {emoji}",
        ]
        return random.choice(templates)


def detect_ambiguous_text_reply(incoming_text: str, ad_title: str = "") -> Dict[str, Any]:
    """تشخیص متن مبهم فروشنده — شما؟ کدوم آگهی؟ بفرمایید؟ — نیاز به شفاف‌سازی"""
    txt = (incoming_text or "").strip()
    low = txt.lower()
    if not txt:
        return {"need_clarify": False, "message": ""}
    # الگوهای مبهم
    ambiguous_patterns = [
        r"^\s*شما\s*\?*\s*$",  # شما؟
        r"شما\s*کی(ستید| هستید)",
        r"کی\s*هستید",
        r"کدوم\s*آگهی",
        r"کدوم\s*اگهی",
        r"کدوم\s*مورد",
        r"کدام\s*آگهی",
        r"بفرمایید\s*\?*",
        r"جانم\s*\?*",
        r"بله\s*\?",
        r"چیکار\s*دارید",
        r"چی\s*میخوای",
        r"چی\s*می‌خوای",
        r"who\s*are\s*you",
        r"which\s*ad",
    ]
    for pat in ambiguous_patterns:
        if re.search(pat, low):
            clarify = (
                f"سلام بزرگوار وقتتون بخیر 🙏\n"
                f"ببخشید من به تعداد زیادی آگهی پیام دادم، شما مربوط به کدوم آگهی هستید؟\n"
                f"اگر لطف کنید عنوان آگهی یا قیمتش رو بگید ممنون می‌شم — من برای «{ad_title[:50] or 'آگهی شما'}» پیام داده بودم."
            )
            return {"need_clarify": True, "is_ambiguous_text": True, "incoming_text": txt, "message": clarify, "pattern": pat}
    # اگر متن خیلی کوتاه و بدون کلمه آگهی (1-2 کلمه)
    if len(txt) <= 6 and txt in ["شما؟", "شما", "بفرما", "بفرمایید", "جانم", "بله؟", "الو؟", "الو", "؟", "?"]:
        clarify = (
            f"سلام وقت بخیر\n"
            f"من برای «{ad_title[:50] or 'آگهی شما'}» پیام داده بودم، شما مربوط به همین آگهی هستید؟ اگر عنوان آگهی رو بگید ممنون می‌شم 🙏"
        )
        return {"need_clarify": True, "is_ambiguous_text": True, "incoming_text": txt, "message": clarify, "pattern": "short"}
    return {"need_clarify": False, "message": ""}

def detect_second_sim_reply(incoming_phone: str, original_ad_phone: str, ad_token: str = "", ad_title: str = "", incoming_text: str = "") -> Dict[str, Any]:
    """تشخیص پاسخ با سیم دوم + متن مبهم — اگر شماره یکی نیست یا فروشنده گفت شما؟ گیج نمی‌زند"""
    inc = (incoming_phone or "").strip()
    orig = (original_ad_phone or "").strip()
    text = (incoming_text or "").strip()

    # اول چک متن مبهم — حتی اگر شماره یکی باشد، ممکن است فروشنده گیج شده باشد
    if text:
        amb = detect_ambiguous_text_reply(text, ad_title=ad_title)
        if amb.get("need_clarify"):
            return {
                "is_second_sim": False,
                "is_ambiguous_text": True,
                "need_clarify": True,
                "incoming": inc,
                "original": orig,
                "ad_token": ad_token,
                "ad_title": ad_title,
                "incoming_text": text,
                "message": amb["message"],
                "log": f"متن مبهم تشخیص: «{text}» برای آگهی {ad_title[:40]}"
            }

    if not inc or not orig:
        # اگر شماره‌ها نیست ولی متن مبهم بود بالا برگشت، اینجا نیاز نیست
        return {"is_second_sim": False, "need_clarify": False, "message": ""}

    # نرمال‌سازی
    def norm(p):
        return re.sub(r"\D", "", p)[-10:]  # 10 رقم آخر

    if norm(inc) == norm(orig):
        return {"is_second_sim": False, "need_clarify": False, "message": ""}

    # سیم دوم تشخیص داده شد
    clarify_msg = (
        f"سلام وقت بخیر\n"
        f"ببخشید من به تعداد زیادی آگهی پیام دادم، شما مربوط به کدوم آگهی هستید؟ "
        f"چون شماره‌ای که پاسخ دادید با شماره آگهی یکی نیست (احتمالاً با سیم دوم پاسخ دادید). "
        f"اگر لطف کنید عنوان آگهی یا قیمتش رو بگید ممنون می‌شم تا سریع‌تر راهنمایی کنم. 🙏"
    )
    return {
        "is_second_sim": True,
        "need_clarify": True,
        "incoming": inc,
        "original": orig,
        "ad_token": ad_token,
        "ad_title": ad_title,
        "message": clarify_msg,
        "log": f"سیم دوم تشخیص: آگهی {ad_token} اصلی {orig} → پاسخ از {inc}"
    }

def detect_second_sim_reply_from_text_only(incoming_text: str, ad_title: str = "") -> Dict[str, Any]:
    """wrapper برای تست فقط متنی — شما؟"""
    return detect_ambiguous_text_reply(incoming_text, ad_title=ad_title)


# ------------------------------------------------ ایجنت تعاملی شکار — نسخه حرفه‌ای
class TiraAgent:
    """ایجنت تیرا — تسلط کامل به سیستم + تحقیق بازار + شکار"""

    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.state: Dict[str, Any] = {
            "messages": [],
            "step": "start",  # start, ask_variants, ask_condition_new_used, ask_sell_price, ask_profit, ask_scratch, confirm, done
            "product": "",
            "research": None,
            "variants_selected": [],
            "variants_all": [],
            "current_variant_idx": 0,
            "answers": {},  # variant -> {sell_price, profit_pct, profit_toman, is_new, is_not_active, scratch, battery, register, repaired, ...}
            "global_profit_pct": None,
            "global_sell_price": None,
            "quantity": 1,
            "conditions": [],
        }

    def reset(self):
        self.state = {
            "messages": [],
            "step": "start",
            "product": "",
            "research": None,
            "variants_selected": [],
            "variants_all": [],
            "current_variant_idx": 0,
            "answers": {},
            "global_profit_pct": None,
            "global_sell_price": None,
            "quantity": 1,
            "conditions": [],
        }

    def _add(self, role: str, text: str):
        self.state["messages"].append({"role": role, "text": text, "at": time.strftime("%H:%M:%S")})

    def start(self, initial_product: str = "") -> Dict[str, Any]:
        self.reset()
        if initial_product:
            return self.handle_user(initial_product)
        msg = (
            "سلام رفیق گل! من تیرا هستم 🧠 دستیار شکار حرفه‌ای و ایجنت کامل سیستم.\n\n"
            "به همه جا مسلطم: پنل SMS ملی‌پیامک، تنظیمات، دیوار+شیپور، اینترنت واقعی (ترب)، تحقیق بازار ایران 1403.\n\n"
            "بگو دنبال چی هستی؟ مثلاً بگو «سری 13 14 15 شکار کن» یا «پراید تمیز» یا هر کالایی — من تحقیق می‌کنم، واریانت‌ها رو جدا میارم، قیمت روز می‌گیرم، پارامترها رو می‌پرسم و تنظیمات شکارچی رو می‌سازم. 🚀"
        )
        self._add("assistant", msg)
        return {"reply": msg, "messages": list(self.state["messages"]), "state": self.state["step"], "research": None}

    def _parse_series(self, text: str) -> List[str]:
        return get_all_iphone_series_from_text(text)

    def try_system_control(self, user_text: str) -> Optional[Dict[str, Any]]:
        """اگر کاربر گفت فلان تنظیم رو ست کن، خودش ست کنه نه فقط راهنمایی"""
        low = user_text.lower()
        txt = user_text.strip()
        # نگاشت تنظیمات فارسی به کلید
        setting_map = {
            "سقف روزانه": "ip_daily_limit",
            "سقف کل": "ip_daily_limit",
            "سقف آی پی": "ip_daily_limit",
            "سقف هر اکانت": "per_account_daily_limit",
            "سقف اکانت": "per_account_daily_limit",
            "فاصله شماره": "phone_delay_sec",
            "فاصله شماره‌گیری": "phone_delay_sec",
            "فاصله اسکن": "watch_interval_sec",
            "دوره اسکن": "watch_interval_sec",
            "سرد شدن": "cooldown_on_block_min",
            "کولدان": "cooldown_on_block_min",
            "پیامک خودکار": "sms_auto_on_new",
            "چت خودکار": "chat_auto_on_new",
            "ارسال خودکار پیامک": "sms_auto_on_new",
            "ارسال خودکار چت": "chat_auto_on_new",
            "تطبیقی": "adaptive_until_captcha",
            "adaptive": "adaptive_until_captcha",
        }
        # تشخیص دستور ست کردن
        # الگو: X رو بذار Y / X = Y / ست کن X Y
        for fa_key, eng_key in setting_map.items():
            if fa_key in txt or fa_key in low:
                # استخراج عدد
                import re
                m = re.search(r"(\d+(?:\.\d+)?)", txt)
                # برای بولین
                if "روشن" in low or "فعال" in low:
                    val = True
                elif "خاموش" in low or "غیرفعال" in low:
                    val = False
                elif m:
                    try:
                        num = float(m.group(1))
                        # اگر اعشاری و مربوط به ثانیه نیست، int کن
                        if eng_key in ("watch_interval_sec", "phone_delay_sec", "per_account_daily_limit", "ip_daily_limit", "cooldown_on_block_min"):
                            val = int(num) if num >= 1 else num
                            # اگر کاربر گفت 100 و مربوط به سقف روزانه، همان 100
                            # اگر فاصله را به ثانیه گفت
                        else:
                            val = bool(num) if eng_key in ("sms_auto_on_new", "chat_auto_on_new", "adaptive_until_captcha") else num
                    except:
                        val = None
                else:
                    val = None
                if val is not None:
                    try:
                        from .store import settings_set, settings_all
                        import os
                        db_path = os.environ.get("DIVAR_DB_PATH", "data/divar_leads.db")
                        settings_set(db_path, eng_key, val)
                        # پیام تایید
                        reply = f"✅ تنظیم «{fa_key}» ({eng_key}) رو خودم ست کردم روی {val} — ذخیره شد و از الان اعمال می‌شه."
                        self._add("assistant", reply)
                        return {"reply": reply, "messages": list(self.state["messages"]), "step": "system_control", "action": {"key": eng_key, "value": val, "ok": True}}
                    except Exception as e:
                        reply = f"❌ نتونستم تنظیم {fa_key} رو ست کنم: {e}"
                        self._add("assistant", reply)
                        return {"reply": reply, "messages": list(self.state["messages"]), "step": "system_control", "error": str(e)}

        # دستور کلمه کلیدی: اضافه کن
        if any(w in low for w in ["کلمه کلیدی اضافه", "پایش اضافه", "شکار اضافه", "کلمه اضافه"]):
            # استخراج کلمه
            # فرض: بعد از اضافه کن، کلمه است
            kw = txt.replace("کلمه کلیدی اضافه", "").replace("اضافه کن", "").replace("برای", "").strip()
            if kw:
                try:
                    from .store import keywords_add
                    import os
                    db_path = os.environ.get("DIVAR_DB_PATH", "data/divar_leads.db")
                    keywords_add(db_path, keyword=kw, cities=None, category="", price_min=0, price_max=0, hunter=True)
                    reply = f"✅ کلمه کلیدی «{kw}» رو خودم اضافه کردم — شکارچی فعال شد."
                    self._add("assistant", reply)
                    return {"reply": reply, "messages": list(self.state["messages"]), "step": "system_control", "action": {"type": "keyword_add", "keyword": kw}}
                except Exception as e:
                    reply = f"❌ خطا در افزودن کلمه: {e}"
                    self._add("assistant", reply)
                    return {"reply": reply, "messages": list(self.state["messages"]), "step": "system_control", "error": str(e)}

        # قالب پیام
        if "قالب پیامک" in txt or "قالب چت" in txt:
            # اگر متن قالب را داده
            if "بذار" in txt or "ست کن" in txt or ":" in txt:
                # جدا کردن
                parts = txt.split("بذار")[-1].split("ست کن")[-1].split(":")[-1].strip()
                if len(parts) > 5:
                    channel = "sms" if "پیامک" in txt else "chat"
                    try:
                        from .store import template_set
                        import os
                        db_path = os.environ.get("DIVAR_DB_PATH", "data/divar_leads.db")
                        template_set(db_path, channel=channel, text=parts)
                        reply = f"✅ قالب {channel} رو خودم ست کردم: «{parts[:60]}...»"
                        self._add("assistant", reply)
                        return {"reply": reply, "messages": list(self.state["messages"]), "step": "system_control", "action": {"type": "template_set", "channel": channel}}
                    except Exception as e:
                        pass
        return None

    def handle_user(self, user_text: str) -> Dict[str, Any]:
        user_text = (user_text or "").strip()
        if not user_text:
            return {"reply": "یه چیزی بنویس تا شروع کنیم 😊 مثلاً «آیفون 13 14 15»", "messages": list(self.state["messages"]), "step": self.state["step"]}

        self._add("user", user_text)
        low = user_text.lower()

        # اول چک کن آیا دستور سیستمی مستقیم است — اگر بود خودش ست کنه
        sys_ctrl = self.try_system_control(user_text)
        if sys_ctrl:
            return sys_ctrl

        # v4: دستور اجرایی / راهنما / پایش دسته — قبل از شکار، حتی جمله بلند
        try:
            from .tira_commands import classify_intent, execute_intent
            intent = classify_intent(user_text, self.state)
            executed = execute_intent(intent, agent=self)
            if executed and executed.get("reply"):
                self._add("assistant", executed["reply"])
                executed["messages"] = list(self.state["messages"])
                executed.setdefault("step", intent.get("kind") or self.state.get("step"))
                return executed
        except Exception:
            pass

        # اگر کاربر درباره SMS پرسید (جمله کوتاه بدون کلمات راهنما)
        if any(w in low for w in ["پیامک", "sms", "ملی پیامک", "melipayamak", "خط خدماتی", "پترن"]):
            # اگر سوال کلی درباره SMS است و هنوز محصول نداریم
            if not self.state["product"] or self.state["step"] == "start":
                guide = get_system_guide("sms")
                self._add("assistant", guide)
                return {"reply": guide, "messages": list(self.state["messages"]), "step": "guide_sms", "guide": "sms"}

        # اگر درباره اینترنت/قیمت پرسید
        if any(w in low for w in ["قیمت روز", "ترب", "اینترنت", "قیمتش چنده"]) and len(user_text) < 120:
            # تحقیق سریع
            prod_kw = re.sub(r"قیمت|روز|چنده|\?|؟", "", user_text).strip() or "آیفون 13"
            res = research_any_product(prod_kw)
            prices_txt = "\n".join([f"• {p['model']}: {p['price_million']} میلیون تومان ({p['source']})" for p in res.get("prices", [])[:8]]) or "قیمت از اینترنت پیدا نشد — کش خالی یا بدون اینترنت"
            msg = f"🔍 تحقیق برای «{prod_kw}»:\n\nواریانت‌ها: {', '.join(res.get('variants', [])[:10])}\n\n{res.get('market_note','')}\n\nقیمت‌ها (ترب/وب):\n{prices_txt}\n\nعوامل افت:\n" + "\n".join([f"• {f['label']}: {f['pct']}٪ — {f['research']}" for f in res.get("factors", [])[:8]])
            self._add("assistant", msg)
            return {"reply": msg, "messages": list(self.state["messages"]), "step": "price_info", "research": res}

        step = self.state["step"]

        # مرحله start — تحقیق محصول
        if step == "start":
            # تشخیص محصول
            product_kw = user_text
            research = research_any_product(product_kw)
            self.state["product"] = product_kw
            self.state["research"] = research
            self.state["variants_all"] = research.get("variants") or [product_kw]
            # اگر آیفون و چند سری گفته (13 14 15)
            series = self._parse_series(user_text)
            if series and research.get("type") == "iphone":
                # واریانت‌ها را کامل بساز
                all_vars = []
                for s in series:
                    all_vars.extend(get_iphone_variants(s))
                # یکتا
                uniq = []
                for v in all_vars:
                    if v not in uniq:
                        uniq.append(v)
                self.state["variants_all"] = uniq
                self.state["series"] = series

            variants = self.state["variants_all"]
            if len(variants) > 1:
                # بپرس کدوم واریانت‌ها
                var_list = "\n".join([f"{i+1}. {v}" for i, v in enumerate(variants[:15])])
                msg = (
                    f"عالی! برای «{product_kw}» تحقیق کردم 🔬\n\n"
                    f"فهمیدم این واریانت‌ها وجود داره:\n{var_list}\n\n"
                    f"بازار ایران 1403: {research.get('market_note','')}\n\n"
                    f"منظورت کدوم‌هاست؟ هر سه تا؟ یا فقط پرو و پرومکس؟ یا مثلاً فقط نات‌اکتیو؟\n"
                    f"بگو مثلاً «هر سه تا» یا «فقط پرو مکس» یا «13 پرو و 14 پرو مکس نات‌اکتیو»"
                )
                self.state["step"] = "ask_variants"
                self._add("assistant", msg)
                return {"reply": msg, "messages": list(self.state["messages"]), "step": "ask_variants", "research": research, "variants": variants}
            else:
                # فقط یک واریانت — برو مرحله بعد
                self.state["variants_selected"] = variants
                self.state["step"] = "ask_condition_new_used"
                msg = (
                    f"برای «{variants[0]}» تحقیق کردم:\n{research.get('market_note','')}\n\n"
                    f"قیمت‌های روز (ترب):\n" + "\n".join([f"• {p['model']}: {p['price_million']}م" for p in research.get("prices", [])[:5]]) +
                    f"\n\nدنبال نو می‌گردی یا دست دوم؟ (مثلاً بگو «دست دوم تمیز» یا «نات‌اکتیو/آکبند»)"
                )
                self._add("assistant", msg)
                return {"reply": msg, "messages": list(self.state["messages"]), "step": "ask_condition_new_used", "research": research}

        if step == "ask_variants":
            # کاربر واریانت‌ها را انتخاب کرد
            txt = user_text
            selected = []
            low_txt = txt.lower()
            # اگر گفت هر سه تا / همه / هر 3 سری
            if any(w in low_txt for w in ["هر سه", "هر 3", "همه", "جفت", "همش", "هرسه", "همه‌ش"]):
                selected = self.state["variants_all"][:12]
                if len(self.state["variants_all"]) > 8:
                    selected = self.state["variants_all"][:12]
            else:
                # تشخیص از متن
                # اگر کلمه پرو مکس دارد
                if "پرو مکس" in txt or "promax" in low_txt or "pro max" in low_txt:
                    selected = [v for v in self.state["variants_all"] if "پرو مکس" in v or "Pro Max" in v]
                elif "پرو" in txt and "مکس" not in txt:
                    selected = [v for v in self.state["variants_all"] if "پرو" in v and "مکس" not in v]
                elif "مینی" in txt:
                    selected = [v for v in self.state["variants_all"] if "مینی" in v or "mini" in v.lower()]
                elif "پلاس" in txt:
                    selected = [v for v in self.state["variants_all"] if "پلاس" in v or "plus" in v.lower()]
                else:
                    # سعی کن عددها را بگیری
                    nums = re.findall(r"1[0-5]", txt)
                    if nums:
                        for n in nums:
                            selected.extend([v for v in self.state["variants_all"] if f" {n}" in v or f"{n} " in v or v.endswith(n)])
                    else:
                        # اگر نفهمید، همه را بگیر
                        selected = self.state["variants_all"][:8]
                # نات‌اکتیو
                if "نات" in txt or "not active" in low_txt or "پلمپ" in txt or "آکبند" in txt:
                    # فقط نات‌اکتیو را علامت بزن، ولی واریانت همان می‌ماند
                    self.state["is_not_active"] = True
                # یکتا
                uniq_sel = []
                for v in selected:
                    if v not in uniq_sel:
                        uniq_sel.append(v)
                selected = uniq_sel or self.state["variants_all"][:6]

            self.state["variants_selected"] = selected[:10]
            self.state["current_variant_idx"] = 0
            self.state["step"] = "ask_condition_new_used"
            msg = (
                f"گرفتم! انتخاب شد: {', '.join(selected[:8])} ✅\n\n"
                f"حالا دنبال نو (نات‌اکتیو/پلمپ) می‌گردی یا دست دوم تمیز؟\n"
                f"مثلاً بگو «دست دوم تمیز می‌خوام» یا «نات‌اکتیو فقط»"
            )
            self._add("assistant", msg)
            return {"reply": msg, "messages": list(self.state["messages"]), "step": "ask_condition_new_used", "variants_selected": selected}

        if step == "ask_condition_new_used":
            low_txt = user_text.lower()
            is_new = any(w in low_txt for w in ["نات اکتیو", "not active", "پلمپ", "آکبند", "آک", "نو"])
            is_used = any(w in low_txt for w in ["دست دوم", "کارکرده", "تمیز", "used"])
            # ذخیره
            for var in self.state["variants_selected"]:
                if var not in self.state["answers"]:
                    self.state["answers"][var] = {}
                self.state["answers"][var]["is_new"] = is_new
                self.state["answers"][var]["is_used"] = is_used or not is_new

            # اگر همین پیام شامل قیمت فروش است (مثلاً 25 میلیون میفروشم)، مستقیم برو به سود
            cands = parse_all_price_candidates(user_text, current_model=self.state["variants_selected"][self.state["current_variant_idx"]] if self.state["variants_selected"] else "")
            price_cands = [c for c in cands if not c[1] and c[0] >= 500_000]
            if price_cands:
                cur_var = self.state["variants_selected"][self.state["current_variant_idx"]]
                sell_price = price_cands[0][0]
                if cur_var not in self.state["answers"]:
                    self.state["answers"][cur_var] = {}
                self.state["answers"][cur_var]["sell_price"] = sell_price
                self.state["global_sell_price"] = sell_price
                self.state["step"] = "ask_profit"
                msg = (
                    f"عالی! فروش «{cur_var}» ~{sell_price//1_000_000} میلیون ثبت شد ✅\n\n"
                    f"حالا چقدر می‌خوای روش بکشی؟ سود حداقل چقدر باشه حال می‌کنی؟\n"
                    f"مثلاً بگو «10 درصد» یا «3 میلیون»"
                )
                self._add("assistant", msg)
                return {"reply": msg, "messages": list(self.state["messages"]), "step": "ask_profit", "sell_price": sell_price}

            self.state["step"] = "ask_sell_price"
            cur_var = self.state["variants_selected"][self.state["current_variant_idx"]]
            research = self.state["research"] or {}
            market_price = None
            try:
                market_price = get_market_price_for_model(cur_var)
            except Exception:
                pass
            price_txt = f" (قیمت نو ترب ~{int(market_price)//1_000_000}م)" if market_price else ""
            msg = (
                f"برای «{cur_var}»{price_txt}:\n"
                f"{research.get('market_note','')}\n\n"
                f"به نظرت تو بازار ایران، اگه همه چیزش سالم و اوکی باشه، دست دوم تمیزش حدوداً چقدر می‌ره؟\n"
                f"و خودت می‌خوای چقدر بفروشی؟ مثلاً بگو «25 میلیون می‌فروشم» یا «همین حدود اوکیه»"
            )
            self._add("assistant", msg)
            return {"reply": msg, "messages": list(self.state["messages"]), "step": "ask_sell_price", "current_variant": cur_var, "market_price": market_price}

        if step == "ask_sell_price":
            cur_var = self.state["variants_selected"][self.state["current_variant_idx"]]
            low_check2 = user_text.lower()
            if any(w in low_check2 for w in ["خش", "باتری", "رجیستر", "تعمیر", "کارتن"]) and not any(w in low_check2 for w in ["میلیون", "تومان", "قیمت", "می‌فروشم", "میفروشم"]):
                for v in self.state["variants_selected"]:
                    if v not in self.state["answers"]:
                        self.state["answers"][v] = {}
                    if "sell_price" not in self.state["answers"][v]:
                        self.state["answers"][v]["sell_price"] = self.state.get("global_sell_price") or 25_000_000
                    if "profit_pct" not in self.state["answers"][v]:
                        self.state["answers"][v]["profit_pct"] = self.state.get("global_profit_pct") or 10
                        self.state["answers"][v]["profit_toman"] = int((self.state["answers"][v]["sell_price"]) * 0.10)
                self.state["conditions"] = [user_text]
                self.state["step"] = "confirm"
                return self._build_confirmation()
            # استخراج قیمت
            cands = parse_all_price_candidates(user_text, current_model=cur_var)
            price_cands = [c for c in cands if not c[1] and c[0] >= 500_000]

            sell_price = None
            if price_cands:
                sell_price = price_cands[0][0]
            else:
                # اگر گفت همین اوکیه
                if any(w in low for w in ["اوکیه", "همین", "باشه", "درسته"]):
                    # از قیمت بازار استفاده کن
                    try:
                        mp = get_market_price_for_model(cur_var)
                        if mp:
                            # دست دوم سالم 20٪ زیر نو
                            sell_price = int(mp * 0.80)
                        else:
                            sell_price = 25_000_000
                    except Exception:
                        sell_price = 25_000_000

            if not sell_price:
                if any(w in low for w in ["همین", "اوکیه", "اوکی", "همون", "مثل قبلی", "قبلی"]):
                    sell_price = self.state.get("global_sell_price") or 25_000_000
                if not sell_price and any(w in low for w in ["خش", "باتری", "رجیستر", "تعمیر", "کارتن", "تمیز"]):
                    sell_price = self.state.get("global_sell_price") or 25_000_000
                    if cur_var not in self.state["answers"]:
                        self.state["answers"][cur_var] = {}
                    self.state["answers"][cur_var]["sell_price"] = sell_price
                    self.state["global_sell_price"] = sell_price
                    for v in self.state["variants_selected"]:
                        if v not in self.state["answers"]:
                            self.state["answers"][v] = {}
                        if "sell_price" not in self.state["answers"][v]:
                            self.state["answers"][v]["sell_price"] = sell_price
                        if "profit_pct" not in self.state["answers"][v]:
                            self.state["answers"][v]["profit_pct"] = self.state.get("global_profit_pct") or 10
                            self.state["answers"][v]["profit_toman"] = int(sell_price * (self.state.get("global_profit_pct") or 10) / 100)
                    self.state["step"] = "ask_details"
                    self.state["conditions"] = [user_text]
                    return self._build_confirmation()

            if not sell_price:
                msg = f"قیمت فروش «{cur_var}» رو دقیق نگرفتم 😅 مثلاً بگو «25 میلیون» یا «همین اوکیه». چقدر می‌فروشی؟"
                self._add("assistant", msg)
                return {"reply": msg, "messages": list(self.state["messages"]), "step": "ask_sell_price"}

            # ذخیره
            if cur_var not in self.state["answers"]:
                self.state["answers"][cur_var] = {}
            self.state["answers"][cur_var]["sell_price"] = sell_price
            self.state["global_sell_price"] = sell_price

            # برو سراغ سود
            self.state["step"] = "ask_profit"
            msg = (
                f"عالی! فروش «{cur_var}» ~{sell_price//1_000_000} میلیون ثبت شد ✅\n\n"
                f"حالا چقدر می‌خوای روش بکشی؟ سود حداقل چقدر باشه حال می‌کنی؟\n"
                f"مثلاً بگو «10 درصد» یا «3 میلیون» — درصدی یا تومانی فرقی نداره"
            )
            self._add("assistant", msg)
            return {"reply": msg, "messages": list(self.state["messages"]), "step": "ask_profit", "sell_price": sell_price}

        if step == "ask_profit":
            cur_var = self.state["variants_selected"][self.state["current_variant_idx"]]
            low_check = user_text.lower()
            if any(w in low_check for w in ["خش", "باتری", "رجیستر", "تعمیر", "کارتن", "تمیز", "بدون"]) and not any(w in low_check for w in ["سود", "درصد", "%"]):
                profit_pct = self.state.get("global_profit_pct") or 10
                sell = self.state["answers"].get(cur_var, {}).get("sell_price") or self.state.get("global_sell_price") or 25_000_000
                profit_toman = int(sell * profit_pct / 100)
                for v in self.state["variants_selected"]:
                    if v not in self.state["answers"]:
                        self.state["answers"][v] = {}
                    if "profit_pct" not in self.state["answers"][v]:
                        self.state["answers"][v]["profit_pct"] = profit_pct
                        self.state["answers"][v]["profit_toman"] = profit_toman
                    if "sell_price" not in self.state["answers"][v]:
                        self.state["answers"][v]["sell_price"] = sell
                self.state["conditions"] = [user_text]
                self.state["step"] = "confirm"
                return self._build_confirmation()

            cands = parse_all_price_candidates(user_text, current_model=cur_var)
            pct_cands = [c for c in cands if c[1]]
            price_cands = [c for c in cands if not c[1] and c[0] >= 200_000]

            profit_pct = None
            profit_toman = None
            if pct_cands:
                profit_pct = pct_cands[0][0]
                # تبدیل به تومان
                sell = self.state["answers"].get(cur_var, {}).get("sell_price") or self.state.get("global_sell_price") or 25_000_000
                profit_toman = int(sell * profit_pct / 100)
            elif price_cands:
                # کوچکترین قیمت که کمتر از فروش باشد = سود
                sell = self.state["answers"].get(cur_var, {}).get("sell_price") or 0
                # اگر قیمت کمتر از فروش است، سود است
                for v, _, _ in price_cands:
                    if sell and v < sell:
                        profit_toman = v
                        profit_pct = round(v / sell * 100, 1) if sell else None
                        break
                if not profit_toman:
                    profit_toman = min(price_cands, key=lambda x: x[0])[0]
                    sell = sell or 25_000_000
                    profit_pct = round(profit_toman / sell * 100, 1) if sell else 10

            if not profit_toman and not profit_pct:
                # عدد تنها مثل 10
                m = re.search(r"\b(\d{1,2})\b", user_text)
                if m:
                    try:
                        v = int(m.group(1))
                        if 1 <= v <= 80:
                            # اگر درصد گفته یا عدد کوچک، درصد فرض کن
                            if "درصد" in low or "%" in user_text or v <= 30:
                                profit_pct = v
                                sell = self.state["answers"].get(cur_var, {}).get("sell_price") or 25_000_000
                                profit_toman = int(sell * v / 100)
                            else:
                                profit_toman = v * 1_000_000
                                sell = self.state["answers"].get(cur_var, {}).get("sell_price") or 25_000_000
                                profit_pct = round(profit_toman / sell * 100, 1)
                    except Exception:
                        pass

            if not profit_toman:
                if any(w in low for w in ["همین", "اوکیه", "اوکی", "همون", "مثل قبلی", "قبلی", "10", "همینا"]):
                    if self.state.get("global_profit_pct"):
                        profit_pct = self.state["global_profit_pct"]
                        sell = self.state["answers"].get(cur_var, {}).get("sell_price") or self.state.get("global_sell_price") or 25_000_000
                        profit_toman = int(sell * profit_pct / 100)
                    elif self.state.get("global_sell_price"):
                        profit_pct = 10
                        sell = self.state["answers"].get(cur_var, {}).get("sell_price") or self.state.get("global_sell_price") or 25_000_000
                        profit_toman = int(sell * 0.10)
                if not profit_toman and any(w in low for w in ["خش", "باتری", "رجیستر", "تعمیر", "کارتن", "تمیز", "بدون"]):
                    profit_pct = self.state.get("global_profit_pct") or 10
                    sell = self.state["answers"].get(cur_var, {}).get("sell_price") or self.state.get("global_sell_price") or 25_000_000
                    profit_toman = int(sell * profit_pct / 100)
                    for v in self.state["variants_selected"]:
                        if v not in self.state["answers"]:
                            self.state["answers"][v] = {}
                        if "profit_pct" not in self.state["answers"][v]:
                            self.state["answers"][v]["profit_pct"] = profit_pct
                            self.state["answers"][v]["profit_toman"] = profit_toman
                    self.state["conditions"] = [user_text]
                    self.state["step"] = "confirm"
                    return self._build_confirmation()

            if not profit_toman:
                msg = f"سود «{cur_var}» رو نگرفتم 😅 مثلاً بگو «10 درصد» یا «3 میلیون». چقدر سود می‌خوای؟"
                self._add("assistant", msg)
                return {"reply": msg, "messages": list(self.state["messages"]), "step": "ask_profit"}

            # ذخیره
            self.state["answers"][cur_var]["profit_pct"] = profit_pct
            self.state["answers"][cur_var]["profit_toman"] = profit_toman
            self.state["global_profit_pct"] = profit_pct

            # اگر واریانت‌های دیگر مانده، برو بعدی
            idx = self.state["current_variant_idx"]
            if idx + 1 < len(self.state["variants_selected"]):
                self.state["current_variant_idx"] += 1
                next_var = self.state["variants_selected"][self.state["current_variant_idx"]]
                self.state["step"] = "ask_sell_price"
                # اگر سود جهانی داریم، پیشنهاد بده
                msg = (
                    f"سود {profit_pct or (profit_toman//1_000_000)} برای «{cur_var}» ثبت شد ✅\n\n"
                    f"حالا بریم سراغ «{next_var}» — قیمت فروش سالم چنده؟ (اگر مثل قبلی اوکیه بگو «همین»)"
                )
                self._add("assistant", msg)
                return {"reply": msg, "messages": list(self.state["messages"]), "step": "ask_sell_price", "current_variant": next_var}
            else:
                # همه واریانت‌ها قیمت و سود دارند — برو سراغ خش و جزئیات
                self.state["step"] = "ask_details"
                factors = (self.state["research"] or {}).get("factors") or []
                # مهم‌ترین عوامل را بپرس
                top_factors = [f for f in factors if f.get("pct", 0) < 0][:5]
                q_list = "\n".join([f"• {f['label']}: {f['pct']}٪ افت — {f['question']}" for f in top_factors])
                msg = (
                    f"عالی! همه مدل‌ها ثبت شد 🎯\n\n"
                    f"حالا چند تا جزئیات مهم که روی قیمت تاثیر داره (بازار ایران 1403):\n{q_list}\n\n"
                    f"مثلاً بگو «خش نداشته باشه، باتری بالای 85، رجیستر شده، تعمیر نشده» یا اگر پیش‌فرض اوکیه بگو «همینا اوکیه»\n"
                    f"بعدش می‌تونم تنظیمات دقیق‌تر رو هم ویرایش کنی — هزاران پارامتر دارم"
                )
                self._add("assistant", msg)
                return {"reply": msg, "messages": list(self.state["messages"]), "step": "ask_details", "factors": top_factors}

        if step == "ask_details":
            # کاربر جزئیات خش و ... را گفت
            txt = user_text
            # ذخیره شرایط
            conds = []
            if "خش" in txt:
                conds.append("بدون خش" if "بدون" in txt or "نداشته" in txt else "خش دارد")
            if "باتری" in txt:
                m = re.search(r"باتری.*?(\d{2,3})", txt)
                if m:
                    conds.append(f"باتری بالای {m.group(1)}")
                else:
                    conds.append("باتری بالای 85" if "بالای" in txt or "خوب" in txt else "باتری")
            if "رجیستر" in txt:
                conds.append("رجیستر شده" if "شده" in txt or "داره" in txt else "بدون رجیستر")
            if "تعمیر" in txt:
                conds.append("بدون تعمیر" if "بدون" in txt or "نشده" in txt else "تعمیر شده")
            if "کارتن" in txt:
                conds.append("با کارتن")
            if not conds and any(w in low for w in ["اوکیه", "همین", "پیش فرض", "پیش‌فرض"]):
                conds = ["تمیز، بدون تعمیر، باتری بالای 85، رجیستر شده"]

            self.state["conditions"] = conds
            # برو به تایید نهایی و ساخت تنظیمات
            self.state["step"] = "confirm"
            return self._build_confirmation()

        if step == "confirm":
            low_txt = user_text.lower()
            if any(w in low_txt for w in ["اوکی", "تایید", "حله", "بزن", "بساز", "ست کن", "اره", "باشه"]):
                self.state["step"] = "done"
                cfg = self.build_final_config()
                msg = (
                    f"ترکوندی! 🚀 تنظیمات شکارچی با {len(cfg.get('keywords',[]))} مدل ساخته شد!\n\n"
                    + "\n".join([f"• {k['keyword']}: فروش {k['sell_price']//1_000_000}م، سود {k.get('profit_pct') or (k['profit']//1_000_000)}، حد خرید {k['buy_target']//1_000_000}م" for k in cfg.get("keywords", [])[:8]])
                    + f"\n\nشرایط: {', '.join(self.state.get('conditions',[])) or 'تمیز پیش‌فرض'}\n\n"
                    f"الان دکمه «⭐ ست کردن تنظیمات تیرا» رو بزن تا موتور شکار روشن شه. از اون به بعد تیرا خودش دیوار و شیپور رو می‌گرده، پیامک/چت می‌فرسته، پاسخ با سیم دوم رو تشخیص می‌ده و مودبانه مذاکره می‌کنه تا شکار بگیره! 🎯"
                )
                self._add("assistant", msg)
                return {"reply": msg, "messages": list(self.state["messages"]), "step": "done", "config": cfg, "ready": True, "done": True}
            else:
                # اصلاح
                msg = "چی رو اصلاح کنم؟ قیمت فروش؟ سود؟ واریانت‌ها؟ شرایط؟ بگو تا درست کنم 👇"
                self._add("assistant", msg)
                return {"reply": msg, "messages": list(self.state["messages"]), "step": "confirm"}

        if step == "done":
            cfg = self.build_final_config()
            msg = "تنظیمات آماده‌ست! دکمه ست کردن رو بزن 🚀 اگه چیزی جا مونده بگو تا اضافه کنم"
            self._add("assistant", msg)
            return {"reply": msg, "messages": list(self.state["messages"]), "step": "done", "config": cfg, "ready": True, "done": True}

        # fallback
        msg = "بگو دنبال چی هستی؟ مثلاً «آیفون 13 14 15 شکار کن»"
        self._add("assistant", msg)
        return {"reply": msg, "messages": list(self.state["messages"]), "step": step}

    def _build_confirmation(self) -> Dict[str, Any]:
        cfg = self.build_final_config()
        lines = ["خب بذار جمع‌بندی کنم رفیق 👇\n"]
        for k in cfg.get("keywords", []):
            lines.append(f"• {k['keyword']}: فروش ~{k['sell_price']//1_000_000}م، سود ~{k.get('profit_pct') or (k['profit']//1_000_000)} ({k['profit']//1_000_000}م)، حد خرید ~{k['buy_target']//1_000_000}م")
        lines.append(f"\n🧹 شرایط: {', '.join(self.state.get('conditions',[])) or 'تمیز پیش‌فرض'}")
        lines.append(f"\n📊 تحقیق بازار: {(self.state.get('research') or {}).get('market_note','')[:200]}")
        lines.append("\nدرسته؟ اگه اوکیه بگو «اوکی» یا «حله» تا تنظیمات پیشرفته با هزاران پارامتر بسازم و موتور شکار روشن شه 🙏")
        msg = "\n".join(lines)
        self._add("assistant", msg)
        return {"reply": msg, "messages": list(self.state["messages"]), "step": "confirm", "config": cfg, "ready": False}

    def build_final_config(self) -> Dict[str, Any]:
        """ساخت تنظیمات نهایی شکارچی — هزاران پارامتر"""
        keywords = []
        research = self.state.get("research") or {}
        factors = research.get("factors") or GENERIC_FACTORS

        # adjustments از عوامل تحقیق
        base_adjustments = {f["key"]: f["pct"] for f in factors}

        for var in self.state.get("variants_selected") or self.state.get("variants_all") or [self.state.get("product")]:
            ans = self.state.get("answers", {}).get(var, {})
            sell_price = int(ans.get("sell_price") or self.state.get("global_sell_price") or 25_000_000)
            profit_pct = ans.get("profit_pct") or self.state.get("global_profit_pct") or 10
            profit_toman = ans.get("profit_toman")
            if not profit_toman and profit_pct:
                profit_toman = int(sell_price * profit_pct / 100)
            if not profit_toman:
                profit_toman = int(sell_price * 0.10)

            buy_target = sell_price - profit_toman
            if buy_target <= 0:
                buy_target = int(sell_price * 0.85)

            # good_pct و great_pct بر اساس سود
            pct = profit_toman / sell_price * 100 if sell_price else 10
            good_pct = max(8, min(25, pct * 0.8))
            great_pct = max(12, min(35, pct * 1.2))

            # شرایط خاص — نات‌اکتیو در بازار ایران 1403:
            # ادعای نات‌اکتیو بدون فاکتور معتبر = ریسک فیک = -6% افت، باید ارزان‌تر بخری
            # با فاکتور معتبر = +3% گران‌تر
            # درصد از اینترنت (ترب + دیوار) به‌روز می‌شود نه هاردکد
            is_not_active_claim = ans.get("is_new") or self.state.get("is_not_active") or any("نات" in str(c) or "پلمپ" in str(c) or "آکبند" in str(c) for c in self.state.get("conditions", []))
            if is_not_active_claim:
                good_pct = max(8, min(30, good_pct + 2))
                great_pct = max(12, min(40, great_pct + 3))
                buy_target = int(buy_target * 0.94)
                cond_text = " ".join(self.state.get("conditions", [])).lower()
                if "فاکتور" in cond_text or "رسمی" in cond_text or "گارانتی" in cond_text:
                    buy_target = int(buy_target * 1.03 / 0.94)

            hunter_adv = {
                "good_pct": round(good_pct, 1),
                "great_pct": round(great_pct, 1),
                "suspicious_pct": 50,
                "dealer_mode": True,
                "sell_price": sell_price,
                "profit": profit_toman,
                "profit_percent": profit_pct,
                "buy_target": buy_target,
                "model": var,
                "conditions": self.state.get("conditions", []),
                "adjustments": base_adjustments,
                "factors": factors,
                "is_new": ans.get("is_new", False),
                "is_not_active": self.state.get("is_not_active", False) or ans.get("is_new", False),
                "research": research,
            }

            price_min = int(buy_target * 0.4)
            price_max = int(buy_target * 1.15)

            cat = ""
            rtype = research.get("type") or ""
            if rtype == "iphone":
                cat = "mobile-phones"
            elif rtype == "appliance":
                cat = research.get("category") or "home-kitchen"
            elif rtype == "car":
                cat = "light"
            keywords.append({
                "keyword": var,
                "category": cat,
                "price_min": price_min,
                "price_max": price_max,
                "hunter": True,
                "vip": True,
                "hunter_adv": hunter_adv,
                "sell_price": sell_price,
                "profit": profit_toman,
                "profit_pct": profit_pct,
                "buy_target": buy_target,
            })

        return {
            "product": self.state.get("product"),
            "keywords": keywords,
            "items": [
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
                }
                for k in keywords
            ],
            "conditions": self.state.get("conditions", []),
            "research": research,
            "summary": f"{len(keywords)} مدل تنظیم شد",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

# سشن‌ها
_tira_sessions: Dict[str, TiraAgent] = {}

def get_tira_agent(session_id: str = "default") -> TiraAgent:
    sid = (session_id or "default").strip() or "default"
    if sid not in _tira_sessions:
        _tira_sessions[sid] = TiraAgent(sid)
    return _tira_sessions[sid]


def reset_tira_sessions() -> None:
    _tira_sessions.clear()

# برای تست سریع
if __name__ == "__main__":
    ag = TiraAgent("test")
    print(ag.start()["reply"])
    print(ag.handle_user("آیفون 13 14 15 شکار کن")["reply"])
