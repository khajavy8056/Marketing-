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


def _check_windows_installer() -> None:
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    ps1 = (root / "installer" / "installer.ps1").read_text(encoding="utf-8-sig")
    console = (root / "installer" / "install-console.ps1").read_text(encoding="utf-8-sig")
    bat = (root / "Install-and-Run.bat").read_text(encoding="utf-8-sig", errors="replace")
    raw_ps1 = (root / "installer" / "installer.ps1").read_bytes()
    if not raw_ps1.startswith(b"\xef\xbb\xbf"):
        raise FileNotFoundError("installer.ps1 باید UTF-8 با BOM باشد")
    for needle in ("ProgressBar", "DownloadProgressChanged", "Unblock-File",
                   "main.py --check", "localhost:8642", ".venv", "CreateShortcut",
                   "KhajavyLead", "khajavy-lead-install.log"):
        if needle not in ps1:
            raise FileNotFoundError(f"نصب‌کننده ناقص است — «{needle}» نیست")
    if "installer.ps1" not in bat or "install-console.ps1" not in bat:
        raise FileNotFoundError("Install-and-Run.bat به نصب‌کننده‌ها وصل نیست")
    if "Extract All" not in bat and "Extract the ZIP" not in bat:
        raise FileNotFoundError("هشدار Extract در bat نیست")
    for needle in ("Find-Python", ".venv", "requirements.txt", "main.py --check",
                   "KhajavyLead", "localhost:8642"):
        if needle not in console:
            raise FileNotFoundError(f"نصب کنسولی ناقص است — «{needle}» نیست")


def _check_static_ui() -> None:
    from pathlib import Path
    p = Path(__file__).parent / "web" / "static" / "index.html"
    html = p.read_text(encoding="utf-8")
    if not p.exists() or "دیوار لید" not in html:
        raise FileNotFoundError(f"فایل رابط گرافیکی پیدا نشد: {p}")
    if "kw-category" not in html:
        raise FileNotFoundError("انتخاب دستهٔ دیوار در رابط نیست")


def _check_db() -> None:
    """دیتابیس و جدول‌ها باید بدون خطا ساخته/باز شوند."""
    from marketing_divar.db import connect
    con = connect("data/divar_leads.db")
    con.execute("SELECT COUNT(*) FROM leads").fetchone()
    con.close()


CHECKS += [
    ("فایل رابط گرافیکی فارسی", _check_static_ui),
    ("دسترسی دیتابیس (data/)", _check_db),
    ("نصب‌کننده ویندوز (نوار پیشرفت + venv)", _check_windows_installer),
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
