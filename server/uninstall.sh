#!/usr/bin/env bash
# حذف کامل نسخهٔ سرور (سرویس، Nginx، پوشهٔ نصب). داده‌ها در ~/.local/share نگه‌داری نمی‌شوند
# مگر اینکه DIVAR_DATA_DIR جدا باشد؛ این اسکریپت فقط خود برنامه را حذف می‌کند.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "با sudo اجرا کنید." >&2
  exit 1
fi

INSTALL_DIR="${INSTALL_DIR:-/opt/divar-server}"

systemctl stop divar-server 2>/dev/null || true
systemctl disable divar-server 2>/dev/null || true
rm -f /etc/systemd/system/divar-server.service
rm -f /etc/nginx/sites-enabled/divar /etc/nginx/sites-available/divar
systemctl daemon-reload
systemctl restart nginx 2>/dev/null || true

if [[ "$KEEP_DATA" != "1" ]]; then
  rm -rf "$INSTALL_DIR"
  echo "پوشهٔ $INSTALL_DIR حذف شد (برای نگه‌داشتن: KEEP_DATA=1)"
else
  echo "پوشهٔ $INSTALL_DIR نگه داشته شد"
fi

echo "حذف کامل شد."
