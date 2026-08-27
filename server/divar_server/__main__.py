# -*- coding: utf-8 -*-
"""نقطهٔ ورود نسخهٔ سرور — بدون باز کردن پنجرهٔ مرورگر بومی.

اجرا:  python -m divar_server   (پورت از DIVAR_SERVER_PORT، پیش‌فرض 8642)
"""

from __future__ import annotations

import os

import uvicorn

# پوشهٔ دادهٔ پایدار را بساز و متغیرهای محیطی (DIVAR_DB_PATH و …) را بگذار
from marketing_divar.paths import apply_runtime_paths
apply_runtime_paths()

# ─── فیکس مسیر مرورگر ─────────────────────────────────────────────────────
# apply_runtime_paths برای ویندوز PLAYWRIGHT_BROWSERS_PATH را به پوشهٔ
# ungoogled-chromium می‌برد؛ روی سرور از Chromium رسمی Playwright استفاده
# می‌کنیم. نصب‌کننده آن را در DIVAR_SERVER_PW_PATH نصب می‌کند (یا پیش‌فرض).
_pw = os.environ.get("DIVAR_SERVER_PW_PATH", "")
if _pw:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _pw
else:
    os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)  # پیش‌فرض Playwright

from .app import build_app          # noqa: E402
from . import __version__           # noqa: E402

app = build_app()

PORT = int(os.environ.get("DIVAR_SERVER_PORT", "8642"))
HOST = "0.0.0.0"


def main() -> None:
    # ربات تلگرام + پایش دوره‌ای پازل/بلاک اکانت‌ها (مثل نسخهٔ ویندوز)
    from marketing_divar.web.server import start_background
    start_background()
    print(f"Divar Marketing Server v{__version__} — http://0.0.0.0:{PORT}")
    print("Reverse proxy (Nginx) باید به همین پورت وصل شود.")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
