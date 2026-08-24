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

def _pause_on_crash(msg: str) -> None:
    """پنجرهٔ سیاه ویندوز بعد از خطا بی‌صدا بسته نشود."""
    print(msg)
    if sys.platform == "win32" and "--check" not in sys.argv:
        try:
            input("یک کلید بزنید تا این پنجره بسته شود...")
        except Exception:
            pass


try:
    from marketing_divar.paths import apply_runtime_paths  # noqa: E402
    _data = apply_runtime_paths()
except Exception as e:
    _pause_on_crash(f"شروع برنامه ناموفق بود: {e}")
    raise

if len(sys.argv) > 1 and sys.argv[1] == "--check":
    from marketing_divar.selfcheck import run
    sys.exit(run())

print(f"📁 داده و تنظیمات: {_data}")
try:
    from marketing_divar.web.__main__ import main  # noqa: E402
except Exception as e:
    _pause_on_crash(f"بارگذاری رابط وب ناموفق بود: {e}")
    raise

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _pause_on_crash(f"برنامه متوقف شد: {e}")
        raise
