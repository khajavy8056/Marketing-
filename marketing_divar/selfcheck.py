# -*- coding: utf-8 -*-
"""تست سلامت نصب — قبل از اجرای برنامه، همه اجزا را بررسی می‌کند.

اجرا:  python main.py --check
خروجی: 0 = همه‌چیز سالم | 1 = مشکل وجود دارد (با پیام فارسی)
"""

from __future__ import annotations

import sys

CHECKS = [
    # (نام فارسی، تابع بررسی)
    ("کتابخانه requests (ارتباط با دیوار)", lambda: __import__("requests")),
    ("کتابخانه fastapi (سرور رابط وب)", lambda: __import__("fastapi")),
    ("کتابخانه uvicorn (اجراگر سرور)", lambda: __import__("uvicorn")),
    ("ماژول core سیستم (کلاینت دیوار)", lambda: __import__("marketing_divar.client")),
    ("ماژول مانیتور چنداکانته", lambda: __import__("marketing_divar.monitor")),
    ("ماژول دیتابیس سرنخ‌ها", lambda: __import__("marketing_divar.db")),
    ("ماژول رابط گرافیکی", lambda: __import__("marketing_divar.web.server")),
]


def _check_static_ui() -> None:
    from pathlib import Path
    p = Path(__file__).parent / "web" / "static" / "index.html"
    if not p.exists() or "دیوار لید" not in p.read_text(encoding="utf-8"):
        raise FileNotFoundError(f"فایل رابط گرافیکی پیدا نشد: {p}")


def _check_db() -> None:
    """دیتابیس و جدول‌ها باید بدون خطا ساخته/باز شوند."""
    from marketing_divar.db import connect
    con = connect("data/divar_leads.db")
    con.execute("SELECT COUNT(*) FROM leads").fetchone()
    con.close()


CHECKS += [
    ("فایل رابط گرافیکی فارسی", _check_static_ui),
    ("دسترسی دیتابیس (data/)", _check_db),
]


def run() -> int:
    print("🩺 تست سلامت «دیوار لید»")
    print("─" * 46)
    failed = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"  ✓ {name}")
        except Exception as e:
            failed += 1
            print(f"  ✗ {name} → {e}")
    print("─" * 46)
    if failed:
        print(f"❌ {failed} مورد مشکل دارد — پیام بالا را گزارش دهید")
        return 1
    print("✅ همه اجزا سالم است — آماده اجرا")
    return 0


if __name__ == "__main__":
    sys.exit(run())
