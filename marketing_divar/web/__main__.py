# -*- coding: utf-8 -*-
"""Start the local web panel — python -m marketing_divar.web
Supports --desktop for native Tira window without browser.
"""
import sys
import threading

import uvicorn

from .. import __version__
from ..brand import APP_NAME_EN, PORT
from ..netinfo import listen_urls
from ..paths import apply_runtime_paths

apply_runtime_paths()
from .server import app, start_background  # noqa: E402,F401

HOST = "0.0.0.0"


def main() -> None:
    # اگر --desktop داده شده، مستقیم برو به اپ دسکتاپ
    if "--desktop" in sys.argv or "--tira" in sys.argv or "--app" in sys.argv:
        from ..desktop_app import main as desktop_main
        return desktop_main()

    # اگر pywebview هست و --web نداده، دسکتاپ را ترجیح بده
    if "--web" not in sys.argv:
        try:
            import webview  # noqa: F401
            from ..desktop_app import main as desktop_main
            print("Desktop mode (pywebview) — opening native Tira window")
            return desktop_main()
        except ImportError:
            pass

    info = listen_urls(PORT)
    print(f"{APP_NAME_EN} {__version__} — 🧠 تیرا")
    print(f"This computer:  {info['local']}")
    if info["lan"]:
        print("Phone / other device on the same Wi-Fi:")
        for u in info["lan"]:
            print(f"                {u}")
    else:
        print("LAN address:    (connect this PC to Wi-Fi to see it)")
    print("The panel is Persian. This window stays English.")
    print("Tip: run with --desktop for native window without browser")
    print("Press Ctrl+C to stop.")
    start_background()

    def _open_panel() -> None:
        from ..app_chromium import open_in_app_chromium
        res = open_in_app_chromium(info["local"])
        if res.get("ok"):
            print("Panel opened in app Chromium (not Edge/Chrome).")
        else:
            print(res.get("message") or "App Chromium not ready.")
            print("Open this URL yourself (do not rely on the system default browser):")
            print(" ", info["local"])

    threading.Timer(1.2, _open_panel).start()
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
