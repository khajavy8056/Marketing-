# -*- coding: utf-8 -*-
"""اجرای رابط وب — python -m marketing_divar.web"""
import threading
import webbrowser

import uvicorn

from .server import app, start_background  # noqa: F401

HOST = "0.0.0.0"
PORT = 8642


def main() -> None:
    url = f"http://localhost:{PORT}"
    print(f"🖥️  رابط وب: {url}  (Ctrl+C برای خروج)")
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
