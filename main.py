# -*- coding: utf-8 -*-
"""Entry point — console text is English only.
Supports:
  --install-nlu        download Qwen model with download manager
  --install-chromium   download Chromium with download manager
  --desktop / --tira / --app   open native desktop window (Tira) without browser
  --web                force browser mode (old)
  --check              self check
"""
import os
import sys

if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))


def _pause_on_crash(msg: str) -> None:
    print(msg)
    if sys.platform == "win32" and "--check" not in sys.argv \
            and "--install-chromium" not in sys.argv \
            and "--install-nlu" not in sys.argv:
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

if len(sys.argv) > 1 and sys.argv[1] in ("--desktop", "--tira", "--app"):
    try:
        from marketing_divar.desktop_app import main as desktop_main  # noqa: E402
        sys.exit(desktop_main())
    except Exception as e:
        _pause_on_crash(f"Desktop app failed: {e}")
        raise

print(f"Data folder: {_data}")

# اگر pywebview نصب باشد و کاربر --web نزده، دسکتاپ مستقل زیباتر است
_use_desktop = "--web" not in sys.argv
if _use_desktop:
    try:
        import webview  # noqa: F401
        from marketing_divar.desktop_app import main as desktop_main  # noqa: E402
        print("Desktop mode (pywebview) detected — opening native Tira window")
        try:
            desktop_main()
            sys.exit(0)
        except SystemExit:
            raise
        except Exception as e:
            print(f"Desktop fallback to web: {e}")
    except ImportError:
        pass

try:
    from marketing_divar.web.__main__ import main  # noqa: E402
except Exception as e:
    _pause_on_crash(f"Could not load the web panel: {e}")
    raise

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _pause_on_crash(f"The program stopped: {e}")
        raise
