# -*- coding: utf-8 -*-
"""Entry point v4.1 — Native Windows app, NOT browser — تیرا دسکتاپ مستقل"""
import os
import sys

if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))


def _pause_on_crash(msg: str) -> None:
    print(msg)
    if sys.platform == "win32" and "--check" not in sys.argv \
            and "--install-chromium" not in sys.argv \
            and "--install-nlu" not in sys.argv \
            and "--web" not in sys.argv:
        try:
            input("Press Enter to close this window...")
        except Exception:
            pass


try:
    from marketing_divar.paths import apply_runtime_paths  # noqa: E402
    _data = apply_runtime_paths()
except Exception as e:
    _pause_on_crash(f"Startup failed: {e}")
    raise

if len(sys.argv) > 1 and sys.argv[1] == "--install-nlu":
    from marketing_divar.nlu_model import ensure_installed as _nlu_install
    try:
        path = _nlu_install(log=print)
        print("NLU model:", path)
        sys.exit(0)
    except Exception as e:
        _pause_on_crash(f"NLU install failed: {e}")
        raise

if len(sys.argv) > 1 and sys.argv[1] == "--install-chromium":
    from marketing_divar.app_chromium import ensure_installed
    try:
        path = ensure_installed()
        print("App Chromium:", path)
        sys.exit(0)
    except Exception as e:
        _pause_on_crash(f"Chromium install failed: {e}")
        raise

if len(sys.argv) > 1 and sys.argv[1] == "--check":
    from marketing_divar.selfcheck import run
    sys.exit(run())

if len(sys.argv) > 1 and sys.argv[1] == "--session-view":
    from marketing_divar.session_view import main as session_view_main
    sys.exit(session_view_main(sys.argv[2:]))

# v4.1: اگر --web داده شده، پنل مرورگر قدیمی باز شود، وگرنه دسکتاپ نیتیو
if len(sys.argv) > 1 and sys.argv[1] == "--web":
    print(f"Data folder: {_data} — WEB MODE")
    try:
        from marketing_divar.web.__main__ import main as web_main  # noqa: E402
    except Exception as e:
        _pause_on_crash(f"Could not load the web panel: {e}")
        raise
    if __name__ == "__main__":
        try:
            web_main()
        except Exception as e:
            _pause_on_crash(f"The program stopped: {e}")
            raise
else:
    # حالت پیش‌فرض: دسکتاپ نیتیو ویندوز — پنجره استاندارد مثل هزاران برنامه ویندوز
    print(f"Data folder: {_data} — DESKTOP NATIVE MODE v4.1")
    try:
        from marketing_divar.desktop_app import main as desktop_main  # noqa: E402
    except Exception as e:
        # اگر desktop_app مشکل داشت، fallback به web
        print(f"Desktop app failed to load: {e} — fallback to web")
        try:
            from marketing_divar.web.__main__ import main as web_main
            if __name__ == "__main__":
                web_main()
            sys.exit(0)
        except Exception as e2:
            _pause_on_crash(f"Could not load any panel: {e2}")
            raise

    if __name__ == "__main__":
        try:
            desktop_main()
        except Exception as e:
            _pause_on_crash(f"Desktop app stopped: {e} — trying web fallback")
            try:
                from marketing_divar.web.__main__ import main as web_main
                web_main()
            except Exception as e2:
                _pause_on_crash(f"Both modes failed: {e2}")
                raise
