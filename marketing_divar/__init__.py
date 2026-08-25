# -*- coding: utf-8 -*-
"""سیستم جمع‌آوری سرنخ و شماره تماس از آگهی‌های دیوار."""

__version__ = "2.1.8"

import sys

# ─── فیکس بحرانی ویندوز ───────────────────────────────────────────────
# وقتی خروجی برنامه pipe/redirect شود (مثل نصب‌کننده یا سرور)، ویندوز از
# کدپیج قدیمی (cp1252/cp1256) استفاده می‌کند و چاپ فارسی/ایموجی باعث
# UnicodeEncodeError و کرش می‌شد. جریان‌های خروجی را از ابتدا UTF-8 با
# «جایگزینی ناامن‌ها» می‌کنیم — روی لینوکس هم بی‌اثر و بی‌ضرر است.
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream is not None and hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # هرگز نباید ایمپورت به‌خاطر این به مشکل بخورد
        pass
