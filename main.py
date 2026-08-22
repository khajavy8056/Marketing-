# -*- coding: utf-8 -*-
"""نقطه ورود برنامه — هم برای اجرای ساده (python main.py) هم برای نسخه exe.

در نسخه exe (PyInstaller): پوشه داده‌ها و لاگ‌ها کنار خود فایل exe ساخته می‌شود.
"""
import os
import sys

# اگر نسخه exe است، همه داده‌ها کنار خود exe ذخیره شوند (نه در پوشه موقت ویندوز)
if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))

from marketing_divar.web.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
