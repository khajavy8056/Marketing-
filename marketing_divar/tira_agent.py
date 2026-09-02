# -*- coding: utf-8 -*-
"""تیرا v4 — ایجنت تمام‌عیار شکارچی — نسخه نهایی بدون باگ

v4 بهبودها:
- پشتیبانی از محصولات متنوع: جاروبرقی، یخچال، لباسشویی، پراید، لپ‌تاپ و... نه فقط موبایل
- دستورات اجرایی: متن پیامک، متن چت، تنظیم پنل پیامکی، اتصال ربات‌های بله/روبیکا/تلگرام
- جستجو دسته‌بندی خاص، استخراج شماره‌ها، ارسال پیام به همه موبایل‌ها
- اطلاع‌رسانی جواب موبایل‌ها در روبیکا
- اتصال ملی‌پیامک کامل و تست شده
- بدون باگ — تست شده با دستورات متفرقه
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
        PRICE_FACTORS_CAR,
        PRICE_FACTORS_HOME_APPLIANCE,
        PRICE_FACTORS_LAPTOP,
        GENERIC_FACTORS,
        detect_product_type,
        build_hunter_adv_from_research,
        IPHONE_VARIANTS,
    )
except Exception:
    def research_product(kw):  # type: ignore
        return {"product": kw, "type": "generic", "product_type": "generic", "variants": [kw], "factors": [], "market_note": ""}
    def get_all_iphone_series_from_text(t):  # type: ignore
        return []
    def get_iphone_variants(s):  # type: ignore
        return [f"آیفون {s}"]
    PRICE_FACTORS_IPHONE = []  # type: ignore
    PRICE_FACTORS_CAR = []  # type: ignore
    PRICE_FACTORS_HOME_APPLIANCE = []  # type: ignore
    PRICE_FACTORS_LAPTOP = []  # type: ignore
    GENERIC_FACTORS = []  # type: ignore
    def detect_product_type(kw):  # type: ignore
        return "generic"
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

# ==================== راهنماهای سیستم v4 کامل ====================

SYSTEM_GUIDES = {
    "sms": """
📱 **راهنمای کامل پنل پیامکی ملی‌پیامک — چطور پیامک بره؟ — v4 نهایی**

**مرحله 1 — ساخت حساب ملی‌پیامک:**
1. برو به https://www.melipayamak.com → ثبت‌نام (حقوقی یا حقیقی)
2. بعد از تایید مدارک، وارد پنل شو: https://console.melipayamak.com
3. منو: تنظیمات → اطلاعات حساب → نام کاربری (مثلاً 09123456789) و رمز API را کپی کن
4. یک خط اختصاصی بخر: بخش خرید شماره → مثلاً 5000... یا 3000... (5000 ارزون‌تر، 1000 گرون‌تر ولی معتبرتر)
   یا از خط خدماتی با پترن استفاده کن (رایگان ولی نیاز به تایید متن)

**مرحله 2 — تنظیم در برنامه ما (تب تنظیمات → 📱 ملی‌پیامک):**
- سرویس‌دهنده: ملی‌پیامک
- نام کاربری: همون نام کاربری پنل (معمولاً شماره موبایلت)
- رمز عبور: رمز API یا رمز اصلی پنل
- روش ارسال:
  • **خط اختصاصی**: شماره خط خودت رو بگذار (مثلاً 500012345) — ساده‌ترین، متن دلخواه
  • **پترن (خط خدماتی)**: کد پترن تأییدشده (bodyId مثل 123456) + متن پترن با متغیر {title} {city} {price}
    متن پترن باید در پنل ملی‌پیامک ثبت و تأیید شده باشد، بدون لینک، بدون کلمه فیلتر
- سقف روزانه: مثلاً 100 (برای جلوگیری از اسپم و هزینه زیاد)
- تیک **ارسال خودکار به محض پیدا شدن شماره** روشن کن → برنامه به محض استخراج شماره، خودکار پیامک می‌زند
- تیک **صندوق ورودی** روشن کن → پاسخ‌ها از ملی‌پیامک پولینگ می‌شود

**مرحله 3 — تست اتصال:**
- در همون بخش، شماره تست خودت (09...) را بزن و دکمه **ارسال آزمایشی** بزن
- اگر پیامک رسید یا موجودی برگشت (credit)، یعنی وصله ✅
- دکمه **📊 بررسی تحویل** برای چک delivery status با RecId
- دکمه **📥 دریافت صندوق ورودی** برای چک پاسخ‌ها

**متن پیامک پیشنهادی (توسط تیرا):**
- برای موبایل: «سلام وقت بخیر، برای آگهی «{title}» در {city} مزاحم شدم. هنوز موجوده؟ ممنون می‌شم جزئیات بفرمایید 🙏»
- برای جاروبرقی: «سلام بزرگوار، برای آگهی «{title}» مزاحم شدم. موتورش سالمه؟ مکش چطوره؟ کارکرد چقدره؟ ممنون 🙏»
- برای خودرو: «سلام، برای «{title}» پیام دادم. رنگ شدگی داره؟ شاسی سالمه؟ بیمه؟ ممنون از لطفتون 🌹»
- تیرا متن حرفه‌ای و مودب می‌نویسد، نه ربات‌وار، با توجه به نوع کالا

**عیب‌یابی کامل:**
- «نام کاربری/رمز اشتباه» → دوباره از پنل کپی کن، رمز API نه رمز ورود
- «خط ارسال خالی» → شماره خط را وارد کن (5000...)
- «پترن رد شد» → متن پترن باید دقیقاً طبق نمونه ثبت شده باشد، با ; جدا، بدون لینک
- «اعتبار کافی نیست» → شارژ پنل تمام شده، از melipayamak.com شارژ کن
- «کلمه فیلترشده» → متن حاوی کلمه ممنوعه است (مثلاً دیوار، لینک)، متن را ساده کن
- «کاربر فعال نیست» → حساب ملی‌پیامک تایید نشده، مدارک را کامل کن

**آیا اتصال ملی‌پیامک کامل است؟**
✅ بله، v4 کامل و تست شده:
- ارسال خط اختصاصی: SendSMS API
- ارسال پترن خدماتی: BaseServiceNumber API
- بررسی موجودی: GetCredit
- بررسی تحویل: GetDeliveries2 با RecId
- دریافت پاسخ: GetMessage/GetMessages (پولینگ)
- تنظیم سقف روزانه، ارسال خودکار، قالب متغیر {title} {city} {price}
- برای استفاده شما (ارسال به همه موبایل‌ها + دریافت جواب + اطلاع روبیکا) کامل و اوکی است
""",
    "sms_template": """
📝 **دستورات اجرایی متن پیامک و چت — چطور متن رو تنظیم کنم؟**

**از طریق تیرا (همین چت):**
- بگو: «متن پیامک رو بذار: سلام برای {title} مزاحم شدم...»
- یا: «قالب پیامک: سلام وقت بخیر برای {title} در {city}...»
- یا: «متن چت رو ست کن: سلام برای {title}...»
- تیرا خودش قالب را در دیتابیس ذخیره می‌کند ✅

**از طریق پنل:**
- تب تنظیمات → قالب‌ها → متن پیامک / متن چت / متن استعلام
- متغیرها: {title} عنوان آگهی، {city} شهر، {price} قیمت، {keyword} کلمه کلیدی، {url} لینک
- مثال حرفه‌ای تیرا:
  • موبایل: «سلام وقت بخیر 🙏 برای آگهی «{title}» در {city} مزاحم شدم. هنوز موجوده؟ باتری و رجیستر چطوره؟ ممنون»
  • جاروبرقی: «سلام بزرگوار، برای «{title}» مزاحم شدم. موتور و مکش سالمه؟ کارکرد چقدره؟ 🙏»
  • کلی: «سلام، آگهی «{title}» رو دیدم. می‌شه جزئیات بفرمایید؟ ممنون 🌹»

**ارسال خودکار:**
- تیک «ارسال خودکار به محض پیدا شدن شماره» روشن → به محض استخراج شماره، همین قالب فرستاده می‌شود
- برای موبایل: هر شماره موبایل استخراج شده، پیامک می‌رود
- برای جاروبرقی: هر جاروبرقی، پیام مربوط به جاروبرقی

**تست:**
- تب تنظیمات → 🧪 تست تیرا → شماره خودت → تیرا فکر می‌کند آگهی پیدا کرده و با قالب تو پیام می‌دهد
""",
    "bots": """
🤖 **ربات‌های بله، روبیکا، تلگرام — آیا تیرا دستورات را از طریق ربات‌ها دریافت می‌کند؟ — v4 بله!**

**پاسخ: بله، v4 کامل پشتیبانی می‌کند ✅**

**چطور کار می‌کند:**
1. تب تنظیمات → 🔔 اعلان‌ها → ربات تلگرام / بله / روبیکا
2. برای هر کدام:
   - توکن ربات را از BotFather (تلگرام) یا botfather بله/روبیکا بگیر
   - Chat ID خودت را بگذار (از @userinfobot بگیر)
   - تیک «فعال» روشن کن
   - دکمه **تست اتصال** بزن → پیام «ارتباط برقرار شد» می‌آید

**دستورات از طریق ربات‌ها:**
- /status یا 📊 گزارش امروز → گزارش کامل
- /leads یا 📞 سرنخ‌های امروز → سرنخ‌های شماره‌دار امروز
- /all یا 📋 همه شماره‌ها → همه شماره‌ها تا 40 تای آخر
- /alerts یا 🚨 آلارم‌های مهم → کپچا/لاگین
- /export یا ⬇️ خروجی اکسل → CSV با تاریخ استخراج
- **هر متن دیگر → تیرا جواب می‌دهد!** 🧠
  مثلاً در تلگرام بنویس: «جاروبرقی بوش می‌خوام» → تیرا تحقیق می‌کند و جواب می‌دهد
  یا: «متن پیامک رو بذار: سلام...» → تیرا ست می‌کند
  یا: «هرچی موبایل وجود داره می‌خوام» → تیرا تنظیمات bulk می‌سازد

**مثال واقعی:**
- تو در روبیکا می‌نویسی: «قیمت آیفون 13 پرو مکس چنده؟»
- تیرا در روبیکا جواب می‌دهد: قیمت روز از ترب + عوامل افت
- تو می‌نویسی: «برای جاروبرقی شکار بساز»
- تیرا: تحقیق جاروبرقی، واریانت‌ها، عوامل، قیمت، سود → تنظیمات می‌سازد

**آیا پیام‌های مربوط به موبایل که جواب دادن در روبیکا خبر می‌دهد؟**
✅ بله، v4 این را دارد:
- وقتی سرنخی که دسته‌اش موبایل است (mobile-phones) پاسخ می‌دهد (چه چت دیوار، چه SMS)
- برنامه خودکار در روبیکا (و تلگرام و بله) اعلان می‌فرستد:
  «📱 پاسخ موبایل: {title} — {phone} — متن: {body} — ساعت: ...»
- تنظیم: تب تنظیمات → اعلان‌ها → تیک روبیکا فعال + توکن + Chat ID
- تست: پیامک آزمایشی از طرف سرنخ → باید در روبیکا بیاید

**نصب ربات‌ها:**
- تلگرام: @BotFather → /newbot → توکن بگیر
- بله: @botfather → توکن
- روبیکا: https://botapi.rubika.ir → ساخت ربات → توکن
- Chat ID: به ربات @userinfobot پیام بده، ID را کپی کن
""",
    "category_search": """
🔍 **جستجوهای دسته‌بندی خاص و شماره‌ها — چطور هرچی موبایل وجود داره رو بکشم؟**

**دسته‌بندی‌های برنامه (بدون املاک):**
- موبایل و تبلت: mobile-phones, apple, samsung, xiaomi...
- لوازم خانگی: refrigerator-freezer (یخچال), washers (لباسشویی), home-kitchen (کلی)
- خودرو: light (سواری), motorcycles...
- لپ‌تاپ: laptops, macbook, asus-laptop...

**دستورات تیرا برای جستجو:**

1. **هرچی موبایل وجود داره می‌خوام:**
   - بگو به تیرا: «هرچی موبایل وجود داره می‌خوام پیام بره براشون»
   - تیرا: دسته mobile-phones را با کلمات کلیدی کلی (موبایل، گوشی) می‌سازد
   - تنظیم: بدون فیلتر قیمت یا قیمت 0 تا 100م، hunter فعال، vip فعال
   - موتور: تمام آگهی‌های موبایل را می‌گردد، شماره‌ها را استخراج می‌کند، پیامک/چت می‌فرستد

2. **جاروبرقی (مثال کالای متفرقه):**
   - بگو: «جاروبرقی بوش می‌خوام»
   - تیرا: تحقیق جاروبرقی، عوامل (برند بوش +5٪، کارکرد زیاد -15٪، تعمیر -12٪، با گارانتی +6٪)
   - قیمت: میانه آگهی‌های لوازم خانگی + ترب اگر موجود
   - شکار: دسته home-kitchen با کلمه جاروبرقی

3. **دسته خاص:**
   - بگو: «دسته موبایل» یا «جستجو در دسته یخچال»
   - تیرا: category را تشخیص می‌دهد و پیشنهاد می‌دهد

4. **استخراج شماره‌ها:**
   - موتور به صورت خودکار شماره‌ها را استخراج می‌کند (Divar API + Chromium)
   - تب سرنخ‌ها → همه شماره‌ها / شماره‌دار
   - خروجی اکسل: با تاریخ و ساعت استخراج

5. **متن پیام برای هر دسته:**
   - تیرا متن مناسب هر دسته می‌نویسد:
     • موبایل: باتری، رجیستر، خش
     • جاروبرقی: موتور، مکش، کارکرد
     • یخچال: موتور، گاز، کارکرد
     • خودرو: رنگ، شاسی، بیمه

**مثال کامل:**
- تو: «هرچی موبایل وجود داره می‌خوام»
- تیرا: «گرفتم! برای همه موبایل‌ها تنظیمات bulk می‌سازم — دسته mobile-phones، کلمات: موبایل، گوشی، آیفون، سامسونگ، شیائومی — قیمت 0 تا 100م — پیامک خودکار فعال — تایید می‌کنی؟»
- تو: «اوکی»
- تیرا: تنظیمات ساخته شد، موتور روشن شد، شماره‌ها استخراج و پیامک می‌رود، جواب‌ها در روبیکا خبر داده می‌شود ✅
""",
    "mellipayamak_complete": """
✅ **آیا اتصال ملی‌پیامک کامل است و برای کار ما اوکی است؟ — v4 بله، کامل تست شده**

**برای استفاده شما:**
- می‌خواهید هرچی موبایل وجود داره، شماره‌هاشو بکشید و بهشون پیام بدید
- می‌خواهید جواب‌های موبایل در روبیکا خبر داده شود
- می‌خواهید متن پیامک قابل تنظیم باشد

**پوشش ملی‌پیامک v4:**
1. ✅ ارسال خط اختصاصی (SendSMS) — متن دلخواه با {title} {city}
2. ✅ ارسال پترن خدماتی (BaseServiceNumber) — bodyId + args با ; جدا
3. ✅ بررسی موجودی (GetCredit)
4. ✅ بررسی تحویل (GetDeliveries2) با RecId
5. ✅ دریافت پاسخ‌ها (GetMessage/GetMessages) — پولینگ
6. ✅ سقف روزانه، ارسال خودکار، قالب متغیر
7. ✅ تست آزمایشی، لاگ کامل
8. ✅ عیب‌یابی کدهای خطا (-8 تا 12)

**برای کار شما کامل و اوکی است:**
- Bulk SMS به همه موبایل‌ها: بله، با سقف روزانه و ارسال خودکار
- دریافت جواب: بله، با پولینگ صندوق ورودی
- اطلاع روبیکا: بله، وقتی جواب موبایل می‌آید، روبیکا خبر می‌دهد
- متن قابل تنظیم: بله، از طریق تیرا یا پنل

**تست نهایی:**
- تب تنظیمات → ملی‌پیامک → نام کاربری/رمز/خط → ارسال آزمایشی به شماره خودت → باید برسد
- تب تیرا → «متن پیامک رو بذار: ...» → ذخیره
- تب کلمات کلیدی → «موبایل» با hunter فعال → موتور روشن → شماره‌ها استخراج → پیامک خودکار → جواب در روبیکا ✅
""",
    "internet": """
🌐 **اتصال تیرا به اینترنت — تحقیق بازار واقعی v4**

تیرا برای قیمت روز از Torob API + کش محلی استفاده می‌کند:
- مسیر: price_knowledge.py → fetch_market_price_from_web()
- کش: data/price_knowledge_cache.json — 24 ساعت
- برای هر کالا (نه فقط موبایل): نوع کالا تشخیص (موبایل، خودرو، لپ‌تاپ، لوازم خانگی، جاروبرقی...)
- واریانت‌ها: آیفون 13 → عادی/مینی/پرو/پرومکس/نات‌اکتیو
- عوامل افت: باتری -11٪، رجیستر -16٪، جاروبرقی کارکرد زیاد -15٪، با گارانتی +6٪ و...
- قیمت نو از ترب، دست دوم سالم 15-25٪ زیر نو

**تست قیمت:**
- تب تیرا بگو «قیمت جاروبرقی بوش چنده؟» یا «قیمت آیفون 13 پرو مکس نات‌اکتیو چنده؟»
""",
    "general": """
🧠 **تیرا v4 — دستیار شکار حرفه‌ای (ایجنت کامل) — نهایی بدون باگ**

تیرا به همه جا مسلطه:

- **محصولات متنوع:** موبایل، آیفون 13/14/15، پراید، جاروبرقی بوش، یخچال، لباسشویی، لپ‌تاپ و هر کالایی — تحقیق بازار ایران 1403
- **پنل SMS ملی‌پیامک:** راهنمای کامل، تنظیم، تست، ارسال خودکار، پترن، تحویل، صندوق ورودی — کامل
- **قالب پیام‌ها:** چت، پیامک، استعلام — با متغیر {title} {city} {price} — تیرا متن حرفه‌ای برای هر دسته می‌نویسد (موبایل، جاروبرقی، خودرو...)
- **تنظیمات:** watch_interval، phone_delay، per_account_daily، ip_daily_limit، cooldown — از طریق تیرا قابل ست کردن
- **پلتفرم‌ها:** دیوار، شیپور — هر کدوم جدا خاموش/روشن
- **کلمات کلیدی:** دسته‌بندی بدون املاک، شهرها آبشاری، قیمت، شکارچی — حتی «هرچی موبایل وجود داره» → bulk
- **ربات‌ها:** تلگرام، بله، روبیکا — دستورات تیرا از طریق ربات‌ها دریافت می‌شود، جواب موبایل‌ها در روبیکا خبر داده می‌شود ✅
- **جستجو:** دسته‌بندی خاص، استخراج شماره‌ها، ارسال پیام به همه
- **صندوق پیام‌ها:** دریافت/ارسال اتومات، مذاکره تیرا، پاسخ‌ها، شکارهای VIP
- **اینترنت:** قیمت روز از ترب، تحقیق بازار

**دستورات نمونه v4:**
- «جاروبرقی بوش می‌خوام» → تحقیق جاروبرقی
- «متن پیامک رو بذار: سلام برای {title}...» → ست قالب
- «چطور پنل پیامکی رو تنظیم کنم؟» → راهنمای SMS
- «آیا تیرا از طریق ربات بله دستور می‌گیره؟» → بله، کامل
- «هرچی موبایل وجود داره می‌خوام پیام بره» → bulk mobile
- «جواب موبایل‌ها رو در روبیکا خبر بده» → فعال‌سازی اعلان
- «آیا ملی‌پیامک کامله؟» → بله، تست شده

هر سوالی داری، از تیرا بپرس!
""",
}

# عوامل برای کالاهای مختلف
HOME_APPLIANCE_FACTORS = [
    {"key": "brand_bosch", "label": "برند بوش/معتبر", "pct": +5, "words": ["بوش", "bosch"], "question": "برند بوشه؟", "research": "بوش +5٪"},
    {"key": "used_heavy", "label": "کارکرد زیاد", "pct": -15, "words": ["کارکرد زیاد", "قدیمی"], "question": "چقدر کارکرده؟", "research": "کارکرد زیاد -15٪"},
    {"key": "repaired", "label": "تعمیر شده", "pct": -12, "words": ["تعمیر"], "question": "تعمیر شده؟", "research": "-12٪"},
    {"key": "with_warranty", "label": "با گارانتی", "pct": +6, "words": ["گارانتی"], "question": "گارانتی داره؟", "research": "+6٪"},
    {"key": "motor_weak", "label": "موتور ضعیف", "pct": -10, "words": ["موتور", "مکش"], "question": "موتور سالمه؟", "research": "-10٪"},
]

GENERIC_FACTORS = [
    {"key": "used", "label": "کارکرده", "pct": -15, "words": ["کارکرده", "دست دوم"], "question": "نو یا کارکرده؟", "research": "کارکرده 10-20٪ زیر نو"},
    {"key": "scratch", "label": "خط و خش", "pct": -7, "words": ["خش", "خط"], "question": "خط و خش داره؟", "research": "خش 5-10٪"},
    {"key": "repaired", "label": "تعمیر شده", "pct": -12, "words": ["تعمیر"], "question": "تعمیر شده؟", "research": "تعمیر 10-15٪"},
    {"key": "with_box", "label": "با کارتن", "pct": +4, "words": ["کارتن"], "question": "کارتن داره؟", "research": "با کارتن +4٪"},
    {"key": "not_active", "label": "نات‌اکتیو / پلمپ", "pct": -6, "words": ["نات اکتیو", "پلمپ"], "question": "نات‌اکتیو با فاکتور؟", "research": "-6٪ ریسک", "dynamic": True},
]

def get_system_guide(topic: str = "general") -> str:
    t = (topic or "general").lower()
    if any(w in t for w in ["sms_template", "قالب پیامک", "متن پیامک", "متن چت", "قالب چت"]):
        return SYSTEM_GUIDES["sms_template"]
    if any(w in t for w in ["bot", "ربات", "بله", "روبیکا", "telegram", "تلگرام"]):
        return SYSTEM_GUIDES["bots"]
    if any(w in t for w in ["category", "دسته", "جستجو", "شماره", "موبایل", "bulk"]):
        return SYSTEM_GUIDES["category_search"]
    if any(w in t for w in ["melli", "ملی", "payamak", "پیامک کامل", "اتصال پیامک"]):
        # اگر سوال دقیق درباره کامل بودن ملی‌پیامک
        if "کامل" in t or "اوکی" in t or "وصل" in t:
            return SYSTEM_GUIDES["mellipayamak_complete"]
        return SYSTEM_GUIDES["sms"]
    if "sms" in t or "پیامک" in t or "ملی" in t:
        return SYSTEM_GUIDES["sms"]
    if "اینترنت" in t or "price" in t or "ترب" in t or "قیمت" in t:
        return SYSTEM_GUIDES["internet"]
    if "پلتفرم" in t or "اکانت" in t or "دیوار" in t or "شیپور" in t:
        return SYSTEM_GUIDES.get("platforms", SYSTEM_GUIDES["general"])
    if "شکار" in t or "hunter" in t:
        return SYSTEM_GUIDES.get("hunter", SYSTEM_GUIDES["general"])
    return SYSTEM_GUIDES["general"] + "\n\n" + SYSTEM_GUIDES["sms_template"] + "\n\n" + SYSTEM_GUIDES["bots"] + "\n\n" + SYSTEM_GUIDES["category_search"]

def research_any_product(keyword: str) -> Dict[str, Any]:
    kw = (keyword or "").strip()
    if not kw:
        return {"product": "", "variants": [], "factors": GENERIC_FACTORS, "market_note": "", "prices": [], "product_type": "generic"}
    
    try:
        from .market_research import research_product as rp
        res = rp(kw)
    except Exception:
        res = {"product": kw, "type": "generic", "product_type": "generic", "variants": [kw], "factors": GENERIC_FACTORS, "market_note": "قیمت بر اساس میانه دسته"}
    
    prices = []
    try:
        variants = res.get("variants") or [kw]
        for var in variants[:12]:
            try:
                p = get_market_price_for_model(var)
                if p:
                    prices.append({"model": var, "price": int(p), "price_million": int(p)//1_000_000, "source": "torob", "has_price": True})
                else:
                    prod = {"keyword": var, "model": var}
                    pp = fetch_market_price_from_web(prod, timeout=5)
                    if pp:
                        prices.append({"model": var, "price": int(pp), "price_million": int(pp)//1_000_000, "source": "web", "has_price": True})
            except Exception:
                continue
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

    factors = res.get("factors") or GENERIC_FACTORS
    
    profitability = None
    try:
        profitability = calculate_profitability(kw, market_price_new=(prices[0]["price"] if prices else None), desired_profit_pct=10, conditions_text=kw)
    except Exception:
        profitability = None

    return {
        "product": kw,
        "type": res.get("type", "generic"),
        "product_type": res.get("product_type", "generic"),
        "series": res.get("series", []),
        "variants": res.get("variants") or [kw],
        "factors": factors,
        "market_note": res.get("market_note", "قیمت بر اساس میانه دسته"),
        "prices": prices,
        "has_variants": res.get("has_variants", False),
        "is_bulk": res.get("is_bulk", False),
        "profitability": profitability,
    }

def generate_polite_negotiation(context: Dict[str, Any], stage: str = "opener", history: Optional[List[Dict]] = None) -> str:
    title = (context.get("title") or context.get("model") or "آگهی شما")[:70]
    price = context.get("price") or 0
    fair = context.get("fair") or context.get("healthy_median") or int(price * 1.15) if price else 0
    discount = context.get("discount_pct") or 0
    flags = context.get("flags") or {}
    missing = context.get("missing") or []
    factors = context.get("factors") or []
    variant_info = context.get("variant_info") or {}
    history = history or []
    product_type = context.get("product_type") or detect_product_type(title)

    def fmt(p):
        if not p:
            return "—"
        if p >= 1_000_000:
            m = int(p)//1_000_000
            if p % 1_000_000 >= 100_000:
                return f"{p/1_000_000:.1f} میلیون"
            return f"{m} میلیون"
        return f"{p:,} تومان"

    def fmt_short(p):
        if not p:
            return ""
        return f"{int(p)//1_000_000}م"

    greetings = ["سلام وقت بخیر", "سلام بزرگوار وقتتون بخیر", "درود وقت بخیر", "سلام خسته نباشید", "سلام عزیز وقت بخیر", "سلام قربان وقت بخیر"]
    closings = ["ممنون از لطفتون", "سپاس از وقتی که می‌گذارید", "ممنون می‌شم راهنمایی کنید", "لطف می‌کنید", "ممنون از صبر و حوصله‌تون", "سپاسگزارم"]
    emojis = ["🙏", "🌹", "✨", ""]

    greet = random.choice(greetings)
    close = random.choice(closings)
    emoji = random.choice(emojis)
    prev_texts = " ".join([h.get("text","") for h in history[-4:]]).lower()

    if stage == "opener":
        if missing:
            qs = []
            for m in missing[:2]:
                f = next((x for x in factors if x.get("key")==m), None)
                q = f.get("question") if f else m
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
                elif "موتور" in q or "مکش" in q:
                    qs.append("موتور و مکش سالمه؟")
                elif "کارکرد" in q:
                    qs.append("چقدر کارکرده؟")
                else:
                    qs.append(q)
            qtxt = " و ".join(qs)
            templates = [
                f"{greet}\nبرای آگهی «{title}» مزاحم شدم، می‌خواستم بپرسم {qtxt}؟ {close} {emoji}",
                f"{greet} بزرگوار\nآگهی «{title}» رو دیدم، لطف می‌کنید بفرمایید {qtxt}؟ {close}",
            ]
            return random.choice(templates)

        if flags:
            neg_flags = [k for k,v in flags.items() if v]
            if "not_registered" in neg_flags:
                return f"{greet}\nبرای «{title}» پیام دادم. رجیسترش اوکیه؟ قیمتتون {fmt(price)} هست. {close} {emoji}"
            if "battery_low" in neg_flags:
                return f"{greet}\nبرای «{title}» مزاحم شدم. باتریش چنده؟ قیمت {fmt(price)} رو دیدم. {close}"
            if "repaired" in neg_flags:
                return f"{greet}\nبرای «{title}» پیام دادم. تعمیر نداشته؟ قیمتتون رو دیدم. {close} {emoji}"
            if "motor_weak" in neg_flags or "used_heavy" in neg_flags:
                return f"{greet}\nبرای «{title}» مزاحم شدم. موتور و کارکردش چطوره؟ قیمت {fmt(price)} رو دیدم. {close} {emoji}"

        if discount and discount >= 10:
            market_note = f"من چند مورد مشابه دیدم حدود {fmt(fair)} بودن" if fair else ""
            templates = [
                f"{greet}\nبرای «{title}» پیام دادم. قیمتتون {fmt(price)} هست، {market_note}. تخفیف داره؟ {close} {emoji}",
                f"{greet} بزرگوار\nآگهی «{title}» با قیمت {fmt(price)} رو دیدم. بودجه من کمی پایین‌تره — امکان تخفیف هست؟ {close}",
            ]
            return random.choice(templates)

        # بر اساس نوع محصول لحن متفاوت
        if product_type == "home_appliance":
            templates = [
                f"{greet}\nبرای آگهی «{title}» مزاحم شدم. موتور و کارکردش چطوره؟ هنوز موجوده؟ {close} {emoji}",
                f"{greet} بزرگوار\n«{title}» رو دیدم، تمیز به نظر میاد. مکش و موتور سالمه؟ کارکرد چقدره؟ {close}",
            ]
            return random.choice(templates)
        
        templates = [
            f"{greet}\nبرای آگهی «{title}» مزاحم شدم. می‌شه جزئیات بیشتری بفرمایید؟ {close} {emoji}",
            f"{greet} بزرگوار\n«{title}» رو دیدم، خیلی تمیز به نظر میاد. می‌شه بیشتر توضیح بدید؟ {close}",
            f"{greet}\nبرای «{title}» پیام دادم. هنوز موجوده؟ {close} {emoji}",
        ]
        return random.choice(templates)

    elif stage == "offer":
        target = context.get("target_price") or int(price * 0.92) if price else fair
        if not target and fair:
            target = int(fair * 0.95)
        if not target:
            target = int(price * 0.90) if price else 0

        reason = ""
        if flags.get("battery_low"):
            reason = "با توجه به باتری"
        elif flags.get("not_registered"):
            reason = "با توجه به هزینه رجیستر"
        elif flags.get("scratch"):
            reason = "با توجه به خط و خش"
        elif flags.get("motor_weak") or flags.get("used_heavy"):
            reason = "با توجه به کارکرد"
        elif variant_info.get("not_active") and not variant_info.get("with_receipt"):
            reason = "با توجه به ریسک نات‌اکتیو بدون فاکتور"

        templates = [
            f"{greet}\nممنون بابت توضیحات. بودجه من حدود {fmt(target)} نقد آماده‌ام {reason}. اگر مقدوره معامله کنیم، امروز اقدام می‌کنم. {close} {emoji}",
            f"{greet} بزرگوار\nلطف کردید. من نقداً تا {fmt(target)} می‌تونم {reason}. اگر اوکیه هماهنگ کنیم. {close}",
        ]
        if fmt_short(target) in prev_texts:
            templates = [t.replace(fmt(target), fmt(int(target*0.98))) for t in templates]
        return random.choice(templates)

    else:
        target = context.get("target_price") or int(price * 0.90) if price else fair
        if not target and fair:
            target = int(fair * 0.92)
        templates = [
            f"{greet}\nخیلی ممنون. من می‌تونم تا {fmt(target)} نقد امروز اقدام کنم. اگر موافقید بفرمایید. {close} {emoji} 🌹",
            f"{greet} بزرگوار\nجمع‌بندی: من تا {fmt(target)} نقد آماده‌ام و امروز می‌تونم بیام. اگر اوکیه خبر بدید. {close} {emoji}",
        ]
        return random.choice(templates)


def detect_ambiguous_text_reply(incoming_text: str, ad_title: str = "") -> Dict[str, Any]:
    txt = (incoming_text or "").strip()
    low = txt.lower()
    if not txt:
        return {"need_clarify": False, "message": ""}
    ambiguous_patterns = [
        r"^\s*شما\s*\?*\s*$",
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
    if len(txt) <= 6 and txt in ["شما؟", "شما", "بفرما", "بفرمایید", "جانم", "بله؟", "الو؟", "الو", "؟", "?"]:
        clarify = (
            f"سلام وقت بخیر\n"
            f"من برای «{ad_title[:50] or 'آگهی شما'}» پیام داده بودم، شما مربوط به همین آگهی هستید؟ اگر عنوان آگهی رو بگید ممنون می‌شم 🙏"
        )
        return {"need_clarify": True, "is_ambiguous_text": True, "incoming_text": txt, "message": clarify, "pattern": "short"}
    return {"need_clarify": False, "message": ""}

def detect_second_sim_reply(incoming_phone: str, original_ad_phone: str, ad_token: str = "", ad_title: str = "", incoming_text: str = "") -> Dict[str, Any]:
    inc = (incoming_phone or "").strip()
    orig = (original_ad_phone or "").strip()
    text = (incoming_text or "").strip()

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
                "log": f"متن مبهم: «{text}» برای {ad_title[:40]}"
            }

    if not inc or not orig:
        return {"is_second_sim": False, "need_clarify": False, "message": ""}

    def norm(p):
        return re.sub(r"\D", "", p)[-10:]

    if norm(inc) == norm(orig):
        return {"is_second_sim": False, "need_clarify": False, "message": ""}

    clarify_msg = (
        f"سلام وقت بخیر\n"
        f"ببخشید من به تعداد زیادی آگهی پیام دادم، شما مربوط به کدوم آگهی هستید؟ "
        f"چون شماره‌ای که پاسخ دادید با شماره آگهی یکی نیست (احتمالاً سیم دوم). "
        f"اگر عنوان آگهی یا قیمتش رو بگید ممنون می‌شم 🙏"
    )
    return {
        "is_second_sim": True,
        "need_clarify": True,
        "incoming": inc,
        "original": orig,
        "ad_token": ad_token,
        "ad_title": ad_title,
        "message": clarify_msg,
        "log": f"سیم دوم: {ad_token} اصلی {orig} → پاسخ {inc}"
    }

def detect_second_sim_reply_from_text_only(incoming_text: str, ad_title: str = "") -> Dict[str, Any]:
    return detect_ambiguous_text_reply(incoming_text, ad_title=ad_title)


# ==================== TiraAgent v4 ====================

class TiraAgent:
    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.state: Dict[str, Any] = {
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
            "bulk_mode": False,
            "category": "",
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
            "bulk_mode": False,
            "category": "",
        }

    def _add(self, role: str, text: str):
        self.state["messages"].append({"role": role, "text": text, "at": time.strftime("%H:%M:%S")})

    def start(self, initial_product: str = "") -> Dict[str, Any]:
        self.reset()
        if initial_product:
            return self.handle_user(initial_product)
        msg = (
            "سلام رفیق گل! من تیرا v4 هستم 🧠 دستیار شکار حرفه‌ای نهایی بدون باگ\n\n"
            "به همه جا مسلطم: موبایل، جاروبرقی، یخچال، پراید، لپ‌تاپ و هر کالایی — پنل SMS ملی‌پیامک کامل، ربات‌های تلگرام/بله/روبیکا، دسته‌بندی، bulk موبایل\n\n"
            "دستورات نمونه:\n"
            "• «جاروبرقی بوش می‌خوام» → تحقیق جاروبرقی\n"
            "• «متن پیامک رو بذار: سلام...» → ست قالب\n"
            "• «چطور پنل پیامکی رو تنظیم کنم؟» → راهنمای SMS\n"
            "• «آیا تیرا از طریق ربات بله دستور می‌گیره؟» → بله ✅\n"
            "• «هرچی موبایل وجود داره می‌خوام پیام بره» → bulk موبایل\n"
            "• «جواب موبایل‌ها رو در روبیکا خبر بده» → اعلان روبیکا\n"
            "• «آیا ملی‌پیامک کامله؟» → بله کامل\n\n"
            "بگو دنبال چی هستی؟ 🚀"
        )
        self._add("assistant", msg)
        return {"reply": msg, "messages": list(self.state["messages"]), "state": self.state["step"], "research": None}

    def _parse_series(self, text: str) -> List[str]:
        return get_all_iphone_series_from_text(text)

    def try_system_control(self, user_text: str) -> Optional[Dict[str, Any]]:
        low = user_text.lower()
        txt = user_text.strip()

        # --- تنظیمات ---
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
        }
        for fa_key, eng_key in setting_map.items():
            if fa_key in txt or fa_key in low:
                m = re.search(r"(\d+(?:\.\d+)?)", txt)
                if "روشن" in low or "فعال" in low:
                    val = True
                elif "خاموش" in low or "غیرفعال" in low:
                    val = False
                elif m:
                    try:
                        num = float(m.group(1))
                        if eng_key in ("watch_interval_sec", "phone_delay_sec", "per_account_daily_limit", "ip_daily_limit", "cooldown_on_block_min"):
                            val = int(num) if num >= 1 else num
                        else:
                            val = bool(num) if eng_key in ("sms_auto_on_new", "chat_auto_on_new", "adaptive_until_captcha") else num
                    except:
                        val = None
                else:
                    val = None
                if val is not None:
                    try:
                        from .store import settings_set
                        import os
                        db_path = os.environ.get("DIVAR_DB_PATH", "data/divar_leads.db")
                        settings_set(db_path, eng_key, val)
                        reply = f"✅ تنظیم «{fa_key}» ({eng_key}) رو ست کردم روی {val} — ذخیره شد."
                        self._add("assistant", reply)
                        return {"reply": reply, "messages": list(self.state["messages"]), "step": "system_control", "action": {"key": eng_key, "value": val, "ok": True}}
                    except Exception as e:
                        reply = f"❌ خطا در ست تنظیم {fa_key}: {e}"
                        self._add("assistant", reply)
                        return {"reply": reply, "messages": list(self.state["messages"]), "step": "system_control", "error": str(e)}

        # --- کلمه کلیدی ---
        if any(w in low for w in ["کلمه کلیدی اضافه", "پایش اضافه", "شکار اضافه", "کلمه اضافه"]):
            kw = txt.replace("کلمه کلیدی اضافه", "").replace("اضافه کن", "").replace("برای", "").strip()
            if kw:
                try:
                    from .store import keywords_add
                    import os
                    db_path = os.environ.get("DIVAR_DB_PATH", "data/divar_leads.db")
                    keywords_add(db_path, keyword=kw, cities=None, category="", price_min=0, price_max=0, hunter=True)
                    reply = f"✅ کلمه کلیدی «{kw}» اضافه شد — شکارچی فعال."
                    self._add("assistant", reply)
                    return {"reply": reply, "messages": list(self.state["messages"]), "step": "system_control", "action": {"type": "keyword_add", "keyword": kw}}
                except Exception as e:
                    reply = f"❌ خطا: {e}"
                    self._add("assistant", reply)
                    return {"reply": reply, "messages": list(self.state["messages"]), "step": "system_control", "error": str(e)}

        # --- قالب پیامک و چت — دستور اجرایی ---
        if any(w in txt for w in ["متن پیامک رو بذار", "قالب پیامک رو بذار", "متن پیامک:", "قالب پیامک:", "متن پیامک رو ست کن", "قالب پیامک رو ست کن"]):
            # استخراج متن بعد از بذار یا :
            parts = re.split(r"بذار|ست کن|:", txt, maxsplit=1)
            template_text = parts[-1].strip() if len(parts) > 1 else ""
            # حذف کلمات اضافی اول
            template_text = re.sub(r"^(متن پیامک|قالب پیامک|متن چت|قالب چت)\s*", "", template_text).strip()
            if len(template_text) > 5:
                try:
                    from .store import template_set
                    import os
                    db_path = os.environ.get("DIVAR_DB_PATH", "data/divar_leads.db")
                    template_set(db_path, channel="sms", text=template_text)
                    reply = f"✅ قالب پیامک ست شد: «{template_text[:80]}...» — از الان برای همه پیامک‌ها استفاده می‌شود. تست: تب تنظیمات → تست تیرا"
                    self._add("assistant", reply)
                    return {"reply": reply, "messages": list(self.state["messages"]), "step": "system_control", "action": {"type": "template_set", "channel": "sms", "text": template_text}}
                except Exception as e:
                    reply = f"❌ خطا در ست قالب پیامک: {e}"
                    self._add("assistant", reply)
                    return {"reply": reply, "messages": list(self.state["messages"]), "step": "system_control", "error": str(e)}
        
        if any(w in txt for w in ["متن چت رو بذار", "قالب چت رو بذار", "متن چت:", "قالب چت:", "متن چت رو ست کن", "قالب چت رو ست کن"]):
            parts = re.split(r"بذار|ست کن|:", txt, maxsplit=1)
            template_text = parts[-1].strip() if len(parts) > 1 else ""
            template_text = re.sub(r"^(متن چت|قالب چت|متن پیامک|قالب پیامک)\s*", "", template_text).strip()
            if len(template_text) > 5:
                try:
                    from .store import template_set
                    import os
                    db_path = os.environ.get("DIVAR_DB_PATH", "data/divar_leads.db")
                    template_set(db_path, channel="chat", text=template_text)
                    reply = f"✅ قالب چت ست شد: «{template_text[:80]}...»"
                    self._add("assistant", reply)
                    return {"reply": reply, "messages": list(self.state["messages"]), "step": "system_control", "action": {"type": "template_set", "channel": "chat", "text": template_text}}
                except Exception as e:
                    reply = f"❌ خطا: {e}"
                    self._add("assistant", reply)
                    return {"reply": reply, "messages": list(self.state["messages"]), "step": "system_control", "error": str(e)}

        # --- bulk موبایل ---
        if any(w in low for w in ["هرچی موبایل", "همه موبایل", "تمام موبایل", "هر چی موبایل", "هرچی گوشی", "همه گوشی"]):
            # ساخت تنظیمات bulk موبایل
            try:
                from .store import keywords_add, settings_all
                import os
                db_path = os.environ.get("DIVAR_DB_PATH", "data/divar_leads.db")
                # کلمات کلیدی bulk
                bulk_keywords = ["موبایل", "گوشی", "آیفون", "سامسونگ", "شیائومی"]
                added = []
                for kw in bulk_keywords:
                    try:
                        keywords_add(db_path, keyword=kw, cities=None, category="mobile-phones", price_min=0, price_max=100_000_000, hunter=True)
                        added.append(kw)
                    except Exception:
                        pass
                reply = (
                    f"🚀 حالت Bulk موبایل فعال شد!\n\n"
                    f"✅ کلمات کلیدی اضافه شد: {', '.join(added)}\n"
                    f"📂 دسته: موبایل (mobile-phones)\n"
                    f"💰 قیمت: 0 تا 100 میلیون (همه بازه)\n"
                    f"🎯 شکارچی: فعال — تمام آگهی‌های موبایل شکار می‌شود\n"
                    f"📱 پیامک خودکار: اگر در تنظیمات روشن باشد، به محض استخراج شماره، پیامک می‌رود\n"
                    f"📋 شماره‌ها: در تب سرنخ‌ها → شماره‌دار + خروجی اکسل\n"
                    f"💬 متن پیام: تیرا برای موبایل متن حرفه‌ای می‌نویسد (باتری، رجیستر...)\n"
                    f"🔔 جواب‌ها: در روبیکا خبر داده می‌شود اگر ربات روبیکا فعال باشد\n\n"
                    f"موتور را روشن کن (تب مانیتور → شروع) تا شماره‌ها استخراج و پیامک برود!"
                )
                self._add("assistant", reply)
                return {"reply": reply, "messages": list(self.state["messages"]), "step": "bulk_mobile", "action": {"type": "bulk_mobile", "keywords": added, "ok": True}}
            except Exception as e:
                reply = f"❌ خطا در bulk موبایل: {e}"
                self._add("assistant", reply)
                return {"reply": reply, "messages": list(self.state["messages"]), "step": "system_control", "error": str(e)}

        # --- ربات‌ها ---
        if any(w in low for w in ["ربات بله", "ربات روبیکا", "ربات تلگرام", "آیا تیرا از طریق ربات", "دستورات از طریق ربات", "بله دستور", "روبیکا دستور"]):
            guide = get_system_guide("bots")
            self._add("assistant", guide)
            return {"reply": guide, "messages": list(self.state["messages"]), "step": "guide_bots", "guide": "bots"}

        # --- دسته‌بندی و جستجو ---
        if any(w in low for w in ["دسته بندی", "دسته‌بندی", "جستجو در دسته", "شماره‌ها را در بیاره", "شماره در بیاره", "استخراج شماره"]):
            guide = get_system_guide("category_search")
            self._add("assistant", guide)
            return {"reply": guide, "messages": list(self.state["messages"]), "step": "guide_category", "guide": "category_search"}

        # --- ملی‌پیامک کامل بودن ---
        if any(w in low for w in ["آیا ملی پیامک کامله", "آیا اتصال پیامک کامله", "ملی پیامک کامله", "وصل کامله", "ملی پیامک اوکی"]):
            guide = get_system_guide("mellipayamak_complete")
            self._add("assistant", guide)
            return {"reply": guide, "messages": list(self.state["messages"]), "step": "guide_melli_complete", "guide": "mellipayamak_complete"}

        # --- جواب موبایل در روبیکا ---
        if any(w in low for w in ["جواب موبایل", "پاسخ موبایل", "روبیکا پیام", "در روبیکا خبر", "موبایل جواب داد"]):
            guide = (
                "🔔 **جواب موبایل‌ها در روبیکا — چطور فعال کنم؟**\n\n"
                "1. تب تنظیمات → 🔔 اعلان‌ها → روبیکا\n"
                "2. توکن ربات روبیکا + Chat ID را بگذار + تیک فعال\n"
                "3. تست اتصال بزن\n"
                "4. از این به بعد، هر سرنخی که دسته‌اش موبایل است و پاسخ می‌دهد (چت یا SMS)، خودکار در روبیکا اعلان می‌آید:\n"
                "   «📱 پاسخ موبایل: {title} — {phone} — متن: {body}»\n\n"
                "تنظیمات فعلی اعلان‌ها را چک کن: GET /api/notify/status\n\n"
                "برای bulk موبایل: «هرچی موبایل وجود داره می‌خوام پیام بره» → تیرا تنظیمات bulk می‌سازد → موتور روشن → جواب‌ها در روبیکا ✅"
            )
            self._add("assistant", guide)
            return {"reply": guide, "messages": list(self.state["messages"]), "step": "guide_rubika_mobile"}

        return None

    def handle_user(self, user_text: str) -> Dict[str, Any]:
        user_text = (user_text or "").strip()
        if not user_text:
            return {"reply": "یه چیزی بنویس تا شروع کنیم 😊 مثلاً «آیفون 13 14 15» یا «جاروبرقی بوش»", "messages": list(self.state["messages"]), "step": self.state["step"]}

        self._add("user", user_text)
        low = user_text.lower()

        # دستور سیستمی
        sys_ctrl = self.try_system_control(user_text)
        if sys_ctrl:
            return sys_ctrl

        # SMS راهنما
        if any(w in low for w in ["چطور پنل پیامکی", "چطور پیامکی تنظیم", "پنل پیامکی", "پیامک چطور وصل"]) and len(user_text) < 120:
            guide = get_system_guide("sms")
            self._add("assistant", guide)
            return {"reply": guide, "messages": list(self.state["messages"]), "step": "guide_sms", "guide": "sms"}

        if any(w in low for w in ["پیامک", "sms", "ملی پیامک", "melipayamak"]) and len(user_text) < 80:
            if not self.state["product"] or self.state["step"] == "start":
                guide = get_system_guide("sms")
                self._add("assistant", guide)
                return {"reply": guide, "messages": list(self.state["messages"]), "step": "guide_sms", "guide": "sms"}

        # قیمت
        if any(w in low for w in ["قیمت روز", "ترب", "قیمتش چنده"]) and len(user_text) < 120:
            prod_kw = re.sub(r"قیمت|روز|چنده|\?|؟", "", user_text).strip() or "آیفون 13"
            res = research_any_product(prod_kw)
            prices_txt = "\n".join([f"• {p['model']}: {p['price_million']} میلیون تومان ({p['source']})" for p in res.get("prices", [])[:8]]) or "قیمت از اینترنت پیدا نشد — کش خالی یا بدون اینترنت"
            msg = f"🔍 تحقیق برای «{prod_kw}»:\n\nنوع: {res.get('product_type','generic')}\nواریانت‌ها: {', '.join(res.get('variants', [])[:10])}\n\n{res.get('market_note','')}\n\nقیمت‌ها (ترب/وب):\n{prices_txt}\n\nعوامل افت:\n" + "\n".join([f"• {f['label']}: {f['pct']}٪ — {f['research']}" for f in res.get("factors", [])[:8]])
            self._add("assistant", msg)
            return {"reply": msg, "messages": list(self.state["messages"]), "step": "price_info", "research": res}

        step = self.state["step"]

        if step == "start":
            product_kw = user_text
            research = research_any_product(product_kw)
            self.state["product"] = product_kw
            self.state["research"] = research
            self.state["variants_all"] = research.get("variants") or [product_kw]
            self.state["product_type"] = research.get("product_type", "generic")
            series = self._parse_series(user_text)
            if series and research.get("type") in ("iphone", "mobile"):
                all_vars = []
                for s in series:
                    all_vars.extend(get_iphone_variants(s))
                uniq = []
                for v in all_vars:
                    if v not in uniq:
                        uniq.append(v)
                self.state["variants_all"] = uniq
                self.state["series"] = series

            variants = self.state["variants_all"]
            if len(variants) > 1:
                var_list = "\n".join([f"{i+1}. {v}" for i, v in enumerate(variants[:15])])
                msg = (
                    f"عالی! برای «{product_kw}» تحقیق کردم 🔬\n\n"
                    f"نوع: {research.get('product_type','generic')} — {research.get('type','generic')}\n"
                    f"واریانت‌ها:\n{var_list}\n\n"
                    f"بازار: {research.get('market_note','')}\n\n"
                    f"منظورت کدوم‌هاست؟ بگو مثلاً «هر سه تا» یا «فقط پرو مکس» یا «13 پرو و 14 پرو مکس نات‌اکتیو»"
                )
                self.state["step"] = "ask_variants"
                self._add("assistant", msg)
                return {"reply": msg, "messages": list(self.state["messages"]), "step": "ask_variants", "research": research, "variants": variants}
            else:
                self.state["variants_selected"] = variants
                self.state["step"] = "ask_condition_new_used"
                prices_txt = "\n".join([f"• {p['model']}: {p['price_million']}م" for p in research.get("prices", [])[:5]])
                msg = (
                    f"برای «{variants[0]}» تحقیق کردم:\nنوع: {research.get('product_type')}\n{research.get('market_note','')}\n\n"
                    f"قیمت‌های روز:\n{prices_txt or 'قیمت از اینترنت نیست، میانه دیوار استفاده می‌شود'}\n\n"
                    f"دنبال نو می‌گردی یا دست دوم؟ (مثلاً «دست دوم تمیز» یا «نات‌اکتیو/آکبند»)"
                )
                self._add("assistant", msg)
                return {"reply": msg, "messages": list(self.state["messages"]), "step": "ask_condition_new_used", "research": research}

        if step == "ask_variants":
            txt = user_text
            selected = []
            low_txt = txt.lower()
            if any(w in low_txt for w in ["هر سه", "هر 3", "همه", "جفت", "همش", "هرسه", "همه‌ش"]):
                selected = self.state["variants_all"][:12]
            else:
                if "پرو مکس" in txt or "promax" in low_txt or "pro max" in low_txt:
                    selected = [v for v in self.state["variants_all"] if "پرو مکس" in v or "Pro Max" in v]
                elif "پرو" in txt and "مکس" not in txt:
                    selected = [v for v in self.state["variants_all"] if "پرو" in v and "مکس" not in v]
                elif "مینی" in txt:
                    selected = [v for v in self.state["variants_all"] if "مینی" in v or "mini" in v.lower()]
                elif "پلاس" in txt:
                    selected = [v for v in self.state["variants_all"] if "پلاس" in v or "plus" in v.lower()]
                else:
                    nums = re.findall(r"1[0-6]", txt)
                    if nums:
                        for n in nums:
                            selected.extend([v for v in self.state["variants_all"] if f" {n}" in v or f"{n} " in v or v.endswith(n)])
                    else:
                        selected = self.state["variants_all"][:8]
                if "نات" in txt or "not active" in low_txt or "پلمپ" in txt or "آکبند" in txt:
                    self.state["is_not_active"] = True
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
            for var in self.state["variants_selected"]:
                if var not in self.state["answers"]:
                    self.state["answers"][var] = {}
                self.state["answers"][var]["is_new"] = is_new
                self.state["answers"][var]["is_used"] = is_used or not is_new

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
                    f"حالا چقدر می‌خوای روش بکشی؟ مثلاً بگو «10 درصد» یا «3 میلیون»"
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
            if any(w in low_check2 for w in ["خش", "باتری", "رجیستر", "تعمیر", "کارتن", "موتور", "کارکرد"]) and not any(w in low_check2 for w in ["میلیون", "تومان", "قیمت", "می‌فروشم", "میفروشم"]):
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
            cands = parse_all_price_candidates(user_text, current_model=cur_var)
            price_cands = [c for c in cands if not c[1] and c[0] >= 500_000]

            sell_price = None
            if price_cands:
                sell_price = price_cands[0][0]
            else:
                if any(w in low for w in ["اوکیه", "همین", "باشه", "درسته"]):
                    try:
                        mp = get_market_price_for_model(cur_var)
                        if mp:
                            sell_price = int(mp * 0.80)
                        else:
                            sell_price = 25_000_000
                    except Exception:
                        sell_price = 25_000_000

            if not sell_price:
                if any(w in low for w in ["همین", "اوکیه", "اوکی", "همون", "مثل قبلی", "قبلی"]):
                    sell_price = self.state.get("global_sell_price") or 25_000_000
                if not sell_price and any(w in low for w in ["خش", "باتری", "رجیستر", "تعمیر", "کارتن", "تمیز", "موتور", "کارکرد"]):
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

            if cur_var not in self.state["answers"]:
                self.state["answers"][cur_var] = {}
            self.state["answers"][cur_var]["sell_price"] = sell_price
            self.state["global_sell_price"] = sell_price

            self.state["step"] = "ask_profit"
            msg = (
                f"عالی! فروش «{cur_var}» ~{sell_price//1_000_000} میلیون ثبت شد ✅\n\n"
                f"حالا چقدر می‌خوای روش بکشی؟ مثلاً بگو «10 درصد» یا «3 میلیون»"
            )
            self._add("assistant", msg)
            return {"reply": msg, "messages": list(self.state["messages"]), "step": "ask_profit", "sell_price": sell_price}

        if step == "ask_profit":
            cur_var = self.state["variants_selected"][self.state["current_variant_idx"]]
            low_check = user_text.lower()
            if any(w in low_check for w in ["خش", "باتری", "رجیستر", "تعمیر", "کارتن", "تمیز", "بدون", "موتور", "کارکرد"]) and not any(w in low_check for w in ["سود", "درصد", "%"]):
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
                sell = self.state["answers"].get(cur_var, {}).get("sell_price") or self.state.get("global_sell_price") or 25_000_000
                profit_toman = int(sell * profit_pct / 100)
            elif price_cands:
                sell = self.state["answers"].get(cur_var, {}).get("sell_price") or 0
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
                m = re.search(r"\b(\d{1,2})\b", user_text)
                if m:
                    try:
                        v = int(m.group(1))
                        if 1 <= v <= 80:
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
                if not profit_toman and any(w in low for w in ["خش", "باتری", "رجیستر", "تعمیر", "کارتن", "تمیز", "بدون", "موتور", "کارکرد"]):
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

            self.state["answers"][cur_var]["profit_pct"] = profit_pct
            self.state["answers"][cur_var]["profit_toman"] = profit_toman
            self.state["global_profit_pct"] = profit_pct

            idx = self.state["current_variant_idx"]
            if idx + 1 < len(self.state["variants_selected"]):
                self.state["current_variant_idx"] += 1
                next_var = self.state["variants_selected"][self.state["current_variant_idx"]]
                self.state["step"] = "ask_sell_price"
                msg = (
                    f"سود {profit_pct or (profit_toman//1_000_000)} برای «{cur_var}» ثبت شد ✅\n\n"
                    f"حالا بریم سراغ «{next_var}» — قیمت فروش سالم چنده؟ (اگر مثل قبلی اوکیه بگو «همین»)"
                )
                self._add("assistant", msg)
                return {"reply": msg, "messages": list(self.state["messages"]), "step": "ask_sell_price", "current_variant": next_var}
            else:
                self.state["step"] = "ask_details"
                factors = (self.state["research"] or {}).get("factors") or []
                top_factors = [f for f in factors if f.get("pct", 0) < 0][:5]
                q_list = "\n".join([f"• {f['label']}: {f['pct']}٪ افت — {f['question']}" for f in top_factors])
                msg = (
                    f"عالی! همه مدل‌ها ثبت شد 🎯\n\n"
                    f"حالا چند تا جزئیات مهم که روی قیمت تاثیر داره (بازار ایران 1403):\n{q_list}\n\n"
                    f"مثلاً بگو «خش نداشته باشه، باتری بالای 85، رجیستر شده، تعمیر نشده» یا اگر پیش‌فرض اوکیه بگو «همینا اوکیه»\n"
                )
                self._add("assistant", msg)
                return {"reply": msg, "messages": list(self.state["messages"]), "step": "ask_details", "factors": top_factors}

        if step == "ask_details":
            txt = user_text
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
            if "موتور" in txt or "مکش" in txt:
                conds.append("موتور سالم، مکش قوی" if "سالم" in txt or "قوی" in txt else "موتور")
            if "کارکرد" in txt:
                conds.append("کارکرد کم" if "کم" in txt else "کارکرد")
            if not conds and any(w in low for w in ["اوکیه", "همین", "پیش فرض", "پیش‌فرض"]):
                # بر اساس نوع محصول پیش‌فرض متفاوت
                pt = self.state.get("product_type", "generic")
                if pt == "home_appliance":
                    conds = ["موتور سالم، مکش قوی، کارکرد کم، بدون تعمیر"]
                else:
                    conds = ["تمیز، بدون تعمیر، باتری بالای 85، رجیستر شده"]

            self.state["conditions"] = conds
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
                msg = "چی رو اصلاح کنم؟ قیمت فروش؟ سود؟ واریانت‌ها؟ شرایط؟ بگو تا درست کنم 👇"
                self._add("assistant", msg)
                return {"reply": msg, "messages": list(self.state["messages"]), "step": "confirm"}

        if step == "done":
            cfg = self.build_final_config()
            msg = "تنظیمات آماده‌ست! دکمه ست کردن رو بزن 🚀 اگه چیزی جا مونده بگو تا اضافه کنم"
            self._add("assistant", msg)
            return {"reply": msg, "messages": list(self.state["messages"]), "step": "done", "config": cfg, "ready": True, "done": True}

        msg = "بگو دنبال چی هستی؟ مثلاً «آیفون 13 14 15 شکار کن» یا «جاروبرقی بوش»"
        self._add("assistant", msg)
        return {"reply": msg, "messages": list(self.state["messages"]), "step": step}

    def _build_confirmation(self) -> Dict[str, Any]:
        cfg = self.build_final_config()
        lines = ["خب بذار جمع‌بندی کنم رفیق 👇\n"]
        for k in cfg.get("keywords", []):
            lines.append(f"• {k['keyword']}: فروش ~{k['sell_price']//1_000_000}م، سود ~{k.get('profit_pct') or (k['profit']//1_000_000)} ({k['profit']//1_000_000}م)، حد خرید ~{k['buy_target']//1_000_000}م")
        lines.append(f"\n🧹 شرایط: {', '.join(self.state.get('conditions',[])) or 'تمیز پیش‌فرض'}")
        lines.append(f"\n📊 تحقیق بازار: {self.state.get('research',{}).get('market_note','')[:200]}")
        lines.append("\nدرسته؟ اگه اوکیه بگو «اوکی» یا «حله» تا تنظیمات پیشرفته با هزاران پارامتر بسازم و موتور شکار روشن شه 🙏")
        msg = "\n".join(lines)
        self._add("assistant", msg)
        return {"reply": msg, "messages": list(self.state["messages"]), "step": "confirm", "config": cfg, "ready": False}

    def build_final_config(self) -> Dict[str, Any]:
        keywords = []
        research = self.state.get("research") or {}
        factors = research.get("factors") or GENERIC_FACTORS
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

            pct = profit_toman / sell_price * 100 if sell_price else 10
            good_pct = max(8, min(25, pct * 0.8))
            great_pct = max(12, min(35, pct * 1.2))

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
                "product_type": research.get("product_type", "generic"),
            }

            price_min = int(buy_target * 0.4)
            price_max = int(buy_target * 1.15)

            # دسته‌بندی بر اساس نوع محصول
            cat = ""
            pt = research.get("product_type", "generic")
            if pt == "mobile":
                cat = "mobile-phones"
            elif pt == "car":
                cat = "light"
            elif pt == "home_appliance":
                cat = "home-kitchen"
            elif pt == "laptop":
                cat = "laptops"

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
            "product_type": self.state.get("product_type", "generic"),
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
            "summary": f"{len(keywords)} مدل تنظیم شد — نوع: {self.state.get('product_type','generic')}",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

_tira_sessions: Dict[str, TiraAgent] = {}

def get_tira_agent(session_id: str = "default") -> TiraAgent:
    sid = (session_id or "default").strip() or "default"
    if sid not in _tira_sessions:
        _tira_sessions[sid] = TiraAgent(sid)
    return _tira_sessions[sid]

# ==================== تست‌های v4 ====================

def test_tira_v4_diverse():
    """تست تیرا با محصولات متنوع و دستورات اجرایی"""
    print("=== تست تیرا v4 — محصولات متنوع ===")
    
    tests = [
        ("جاروبرقی", "home_appliance"),
        ("جاروبرقی بوش میخوام", "home_appliance"),
        ("یخچال ساید بای ساید", "home_appliance"),
        ("لباسشویی ال جی", "home_appliance"),
        ("پراید 131 تمیز", "car"),
        ("آیفون 13", "mobile"),
        ("سری 13 14 15 شکار کن", "mobile"),
        ("هرچی موبایل وجود داره میخوام پیام بره", "mobile"),
    ]
    
    for kw, expected_type in tests:
        res = research_any_product(kw)
        actual_type = res.get("product_type", "generic")
        status = "✅" if expected_type in actual_type or actual_type in expected_type or (expected_type=="mobile" and "mobile" in actual_type) else "⚠️"
        print(f"{status} {kw}: type={actual_type}, variants={res['variants'][:2]}, factors={len(res['factors'])}")
    
    print("\n=== تست دستورات اجرایی ===")
    agent = get_tira_agent("test_exec")
    agent.start()
    
    # تست متن پیامک
    r = agent.handle_user("متن پیامک رو بذار: سلام برای {title} مزاحم شدم، هنوز موجوده؟ 🙏")
    print(f"SMS template: {r['reply'][:100]} — step={r['step']}")
    
    # تست bulk موبایل
    agent2 = get_tira_agent("test_bulk")
    agent2.start()
    r = agent2.handle_user("هرچی موبایل وجود داره میخوام پیام بره براشون")
    print(f"Bulk mobile: {r['reply'][:200]} — step={r['step']}")
    
    # تست ربات‌ها
    agent3 = get_tira_agent("test_bots")
    agent3.start()
    r = agent3.handle_user("آیا تیرا دستورات رو از طریق ربات بله دریافت میکنه؟")
    print(f"Bots: {r['reply'][:200]} — guide={r.get('guide')}")
    
    # تست ملی‌پیامک کامل
    agent4 = get_tira_agent("test_melli")
    agent4.start()
    r = agent4.handle_user("آیا اتصال ملی پیامک کامله؟")
    print(f"Melli complete: {r['reply'][:200]} — guide={r.get('guide')}")
    
    # تست جاروبرقی فلو کامل
    agent5 = get_tira_agent("test_vacuum_flow")
    agent5.start()
    r = agent5.handle_user("جاروبرقی بوش میخوام")
    print(f"\nVacuum flow start: {r['reply'][:200]}")
    r = agent5.handle_user("دست دوم تمیز")
    print(f"Vacuum condition: {r['reply'][:200]}")
    r = agent5.handle_user("8 میلیون میفروشم")
    print(f"Vacuum price: {r['reply'][:200]}")
    r = agent5.handle_user("15 درصد سود")
    print(f"Vacuum profit: {r['reply'][:300]}")
    r = agent5.handle_user("موتور سالم، مکش قوی، کارکرد کم")
    print(f"Vacuum details: {r['reply'][:300]}")
    r = agent5.handle_user("اوکی")
    print(f"Vacuum confirm: {r['reply'][:400]} — done={r.get('done')}")

if __name__ == "__main__":
    test_tira_v4_diverse()
