# -*- coding: utf-8 -*-
"""Start the local web panel — python -m marketing_divar.web"""
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
    info = listen_urls(PORT)
    print(f"{APP_NAME_EN} {__version__}")
    print(f"This computer:  {info['local']}")
    if info["lan"]:
        print("Phone / other device on the same Wi-Fi:")
        for u in info["lan"]:
            print(f"                {u}")
    else:
        print("LAN address:    (connect this PC to Wi-Fi to see it)")
    print("The panel is Persian. This window stays English.")
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
