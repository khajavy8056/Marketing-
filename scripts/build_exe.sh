#!/usr/bin/env bash
# ساخت نسخه تک‌فایل لینوکس (روی لینوکس اجرا شود)
set -e
pip install -r requirements.txt pyinstaller
pyinstaller --name DivarLead --onefile \
  --add-data "marketing_divar/web/static:marketing_divar/web/static" \
  marketing_divar/web/__main__.py
echo "خروجی: dist/DivarLead"
