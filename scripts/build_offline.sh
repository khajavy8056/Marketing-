#!/usr/bin/env bash
# 🧠 تیرا - ساخت نصب‌کننده آفلاین در لینوکس
# نوار پیشرفت گرافیکی برای تولید فایل نصب 1-2GB
# خروجی: installer/payload.zip (آفلاین شامل Chromium+Model)

set -e
cd "$(dirname "$0")/.."

echo "============================================"
echo "🧠 تیرا - ساخت نصب‌کننده آفلاین (Linux)"
echo "============================================"
echo "این اسکریپت فایل نصب آفلاین می‌سازد:"
echo "- Chromium + مدل Qwen دانلود می‌شود"
echo "- داخل payload.zip بسته‌بندی می‌شود (1-2GB)"
echo "- در ویندوز با ساخت-نصب-استاندارد.bat به Setup.exe تبدیل می‌شود"
echo ""

# Python
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
elif command -v python3 >/dev/null; then
  PY="python3"
else
  PY="python"
fi

echo "[0/5] Python: $PY"
$PY --version

echo "[1/5] نصب وابستگی‌ها..."
$PY -m pip install -r requirements.txt --disable-pip-version-check -q || \
$PY -m pip install -r requirements.txt -i https://mirror-pypi.runflare.com/simple --disable-pip-version-check -q

echo "[2/5] دانلود Chromium با DownloadManager..."
$PY main.py --install-chromium || echo "[WARN] Chromium will be retried"

echo "[3/5] دانلود مدل تیرا با DownloadManager..."
$PY main.py --install-nlu || echo "[WARN] Model fallback"

echo "[4/5] بسته‌بندی آفلاین (1-2GB)..."
echo "نوار پیشرفت:"
$PY installer/pack_payload.py --offline

echo "[5/5] خلاصه:"
ls -lh installer/payload.zip
echo ""
echo "✅ Payload آفلاین آماده شد"
echo "حجم: $(du -h installer/payload.zip | cut -f1)"
echo ""
echo "برای ساخت Setup.exe رمزنگاری شده در ویندوز:"
echo "  ساخت-نصب-استاندارد.bat"
echo ""
echo "یا در همین لینوکس برای تست:"
echo "  python installer/setup_app.py --cli --dest /tmp/tira-test"
