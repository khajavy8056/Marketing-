# -*- coding: utf-8 -*-
"""نقطه ورود برنامه — هم برای اجرای ساده (python main.py) هم برای نسخه exe.

در نسخه exe (PyInstaller): پوشه داده‌ها و لاگ‌ها کنار خود فایل exe ساخته می‌شود.

حالت‌ها:
  python main.py            → اجرای رابط وب (مرورگر خودکار باز می‌شود)
  python main.py --check    → فقط تست سلامت نصب (برای نصب‌کننده ویندوز)
"""
import os
import sys

# اگر نسخه exe است، کنار خود exe بایست (نه پوشه موقت ویندوز)
if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))

# تنظیمات/اکانت/تلگرام/ملی‌پیامک در پوشه پایدار کاربر می‌مانند
from marketing_divar.paths import apply_runtime_paths  # noqa: E402
_data = apply_runtime_paths()

if len(sys.argv) > 1 and sys.argv[1] == "--check":
    from marketing_divar.selfcheck import run
    sys.exit(run())

print(f"📁 داده و تنظیمات: {_data}")
from marketing_divar.web.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
