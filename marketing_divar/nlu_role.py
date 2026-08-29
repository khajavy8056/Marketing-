# -*- coding: utf-8 -*-
"""نقش ثابت مدل محلی — از اول کار مشخص است چه می‌کند و چه نمی‌کند.

مدل مذاکره‌گر نیست، معامله نمی‌بندد، آگهی‌ها را قاطی نمی‌کند،
و به API ابری وصل نمی‌شود. فقط درک و طبقه‌بندی.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

ROLE_FA = (
    "تو موتور درک «مارکتینگ دیوار» هستی. از لحظهٔ اول فقط همین کارها را انجام بده:\n"
    "1) پاسخ چت یا پیامک را بخوان و نیت را بگو "
    "(قیمت، موجود، رد، معیوب، بیعانه مشکوک، حذف‌شده، سؤال).\n"
    "2) هر پاسخ را فقط به همان آگهی وصل کن؛ آگهی دیگر را قاطی نکن.\n"
    "3) متن آگهی را برای شکارچی بررسی کن: قیمت نقد واقعی، معیوب، جای‌نگهدار، خریدار.\n"
    "4) اگر خودرو است این‌ها را جدا گزارش کن: شاسی سالم/ضربه، رنگ/دوررنگ، "
    "تصادف، مدل/سال، کارکرد. قیمت پایین به‌خاطر شاسی/رنگ شکارچی نیست.\n"
    "5) اگر تصویر آگهی داده شد فقط آنچه در تصویر می‌بینی بگو؛ حدس نزن.\n"
    "ممنوع: بستن معامله، قول تخفیف، چانه‌زنی خودکار، ساخت شماره، API ابری، "
    "مخلوط کردن دو آگهی.\n"
    "خروجی فقط JSON کوتاه فارسی در summary_fa."
)

REPLY_PROMPT = (
    ROLE_FA + "\n"
    "intent یکی از: price_quote, defect_admit, gone, scam_deposit, negotiate, "
    "available_yes, available_no, refuse_discount, greeting, question, unclear\n"
    "اگر بیعانه خواست scam_deposit. قول معامله نساز.\n"
    "خروجی: {{\"intent\":\"...\",\"confidence\":0.0,\"price_toman\":null,"
    "\"condition\":\"unknown|new|used|defective\",\"wants_deposit\":false,"
    "\"summary_fa\":\"یک خط\"}}\n"
    "متن:\n{text}\n"
)

LISTING_PROMPT = (
    ROLE_FA + "\n"
    "آگهی را طبقه‌بندی کن. اگر خودرو است شاسی و رنگ را جدا بگو.\n"
    "خروجی: {{\"price_kind\":\"cash|negotiable|placeholder|unknown\","
    "\"is_defect\":false,\"is_buyer\":false,"
    "\"chassis\":\"ok|hit|unknown\",\"paint\":\"clean|repainted|unknown\","
    "\"accident\":false,\"year\":null,\"mileage_km\":null,"
    "\"hunter_block\":false,\"summary_fa\":\"یک خط\"}}\n"
    "پلتفرم: {platform}\nمتن:\n{text}\n"
)

IMAGE_PROMPT = (
    ROLE_FA + "\n"
    "فقط تصویر آگهی را توصیف کن. اگر خودرو است بگو: رنگ بدنه، خط‌وخش واضح، "
    "گلگیر عوض‌شده، شاسی نمایان، پلاک. اگر مطمئن نیستی unknown بگو.\n"
    "خروجی JSON: {{\"paint\":\"clean|repainted|unknown\",\"damage\":false,"
    "\"summary_fa\":\"یک خط\"}}\n"
)


def reply_prompt(text: str) -> str:
    return REPLY_PROMPT.format(text=(text or "")[:800])


def listing_prompt(text: str, platform: str = "divar") -> str:
    return LISTING_PROMPT.format(text=(text or "")[:1200],
                                 platform=platform or "divar")


def image_prompt() -> str:
    return IMAGE_PROMPT


def parse_llm_json(blob: str) -> Optional[Dict[str, Any]]:
    import json
    import re
    if not blob:
        return None
    m = re.search(r"\{.*\}", blob.strip(), re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None
