# -*- coding: utf-8 -*-
"""پیکربندی سیستم — مقادیر پیش‌فرض محافظه‌کارانه (زیر آستانه‌های بلاک دیوار)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

DEFAULTS: Dict[str, Any] = {
    # --- نرخ‌ها: زیر آستانه‌های گزارش‌شده دیوار (~7 شماره/دقیقه) ---
    "phone_delay_sec": 10,        # ≥10s → حداکثر ~6 شماره در دقیقه
    "jitter_sec": 4,              # تصادفی‌بودن تاخیر (رفتار انسانی)
    "search_delay_sec": 5,
    "search_page_delay_sec": 8,
    # --- سهمیه روزانه ---
    "phone_daily_limit": 80,      # سقف گزارش‌شده ۱۵۰؛ محافظه‌کارانه
    "search_daily_limit": 300,
    # --- چند اکانت و مانیتور لحظه‌ای ---
    "watch_interval_sec": 300,    # هر ۵ دقیقه جستجوی آگهی‌های جدید
    "per_account_daily_limit": 129,  # سقف نرم هر اکانت؛ بعدش اگر دیوار کپچا ندهد ادامه
    "adaptive_until_captcha": True,  # بعد از سقف نرم، تا کپچا/۴۲۹ دیوار ادامه بده
    "ip_daily_limit": 240,        # سقف کلی همه اکانت‌ها از یک IP (محافظ اکانت‌ها)
    # --- قطع‌کننده مدار (Circuit Breaker) ---
    "cooldown_on_block_min": 30,  # توقف بعد از اولین 429/کپچا
    "backoff_multiplier": 1.5,    # هر توقف، سرعت را کمتر می‌کند
    "max_consecutive_blocks": 3,  # بعد از این تعداد، توقف تا فردا
    # --- اعلان ---
    "notify": {"telegram_bot_token": "", "telegram_chat_id": ""},
    # --- پیام چت نیمه‌خودکار ---
    "chat_template": (
        "سلام، وقتتون بخیر 🌹\n"
        "آگهی «{title}» رو دیدم. "
        "اگر هنوز به نتیجه نرسیدید، خوشحال می‌شوم چند دقیقه صحبت کنیم.\n"
        "ممنون از وقتی که می‌گذارید 🙏"
    ),
    # --- سایر ---
    "interactive": True,          # هنگام کپچا از اپراتور بخواه حل کند
}


def load_config(path: str | None = None) -> Dict[str, Any]:
    """config.json روی پیش‌فرض‌ها سوار می‌شود (بدون آن هم کار می‌کند)."""
    cfg = json.loads(json.dumps(DEFAULTS))  # کپی عمیق
    p = Path(path or os.environ.get("DIVAR_CONFIG_PATH") or "config.json")
    if p.exists():
        try:
            user = json.loads(p.read_text(encoding="utf-8"))
            for k, v in user.items():
                if k == "notify" and isinstance(v, dict):
                    cfg["notify"].update(v)
                else:
                    cfg[k] = v
        except (ValueError, OSError) as e:
            print(f"[!] config.json خوانده نشد ({e})؛ پیش‌فرض‌ها استفاده می‌شوند")
    # امکان تغییر از متغیر محیطی
    if os.environ.get("DIVAR_PHONE_DAILY_LIMIT"):
        cfg["phone_daily_limit"] = int(os.environ["DIVAR_PHONE_DAILY_LIMIT"])
    if os.environ.get("DIVAR_PHONE_DELAY"):
        cfg["phone_delay_sec"] = float(os.environ["DIVAR_PHONE_DELAY"])
    return cfg
