# -*- coding: utf-8 -*-
"""Entry point — console text is English only."""
import os
import sys

if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))


def _pause_on_crash(msg: str) -> None:
    print(msg)
    if sys.platform == "win32" and "--check" not in sys.argv:
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

print(f"Data folder: {_data}")
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
