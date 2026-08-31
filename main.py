# -*- coding: utf-8 -*-
"""🧠 تیرا — Entry point
- پیش‌فرض: دسکتاپ مستقل (pywebview) اگر نصب باشد
- --desktop / --tira: پنجره مستقل
- --web: حالت مرورگر قدیمی
- --install-nlu / --install-chromium: دانلود با DownloadManager
"""
import os
import sys

if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))

def _pause(msg: str):
    print(msg)
    if sys.platform == "win32" and "--check" not in sys.argv:
        try:
            input("Press Enter...")
        except Exception:
            pass

try:
    from marketing_divar.paths import apply_runtime_paths
    _data = apply_runtime_paths()
except Exception as e:
    _pause(f"Startup failed: {e}")
    raise

if len(sys.argv) > 1 and sys.argv[1] == "--install-nlu":
    from marketing_divar.nlu_model import ensure_installed
    try:
        p = ensure_installed(log=print)
        print(f"NLU: {p}")
        sys.exit(0)
    except Exception as e:
        _pause(f"NLU failed: {e}")
        raise

if len(sys.argv) > 1 and sys.argv[1] == "--install-chromium":
    from marketing_divar.app_chromium import ensure_installed
    try:
        p = ensure_installed()
        print(f"Chromium: {p}")
        sys.exit(0)
    except Exception as e:
        _pause(f"Chromium failed: {e}")
        raise

if len(sys.argv) > 1 and sys.argv[1] == "--check":
    from marketing_divar.selfcheck import run
    sys.exit(run())

if len(sys.argv) > 1 and sys.argv[1] in ("--desktop", "--tira", "--app"):
    try:
        from marketing_divar.desktop_app import main as desktop_main
        sys.exit(desktop_main())
    except Exception as e:
        _pause(f"Desktop failed: {e}")
        raise

print(f"Data folder: {_data}")

# اگر pywebview هست و --web نداده، دسکتاپ
if "--web" not in sys.argv:
    try:
        import webview
        from marketing_divar.desktop_app import main as desktop_main
        print("Desktop mode (native window) — Tira")
        desktop_main()
        sys.exit(0)
    except ImportError:
        pass
    except SystemExit:
        raise
    except Exception as e:
        print(f"Desktop fallback to web: {e}")

try:
    from marketing_divar.web.__main__ import main
except Exception as e:
    _pause(f"Could not load web panel: {e}")
    raise

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _pause(f"Stopped: {e}")
        raise
