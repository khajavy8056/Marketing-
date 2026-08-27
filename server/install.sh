#!/usr/bin/env bash
# =============================================================================
#  نصب‌کنندهٔ یک‌دستوری نسخهٔ سرور لینوکسی «مارکتینگ دیوار»
# -----------------------------------------------------------------------------
#  از صفر تا صد: آپدیت/آپگرید سرور → نصب پیش‌نیازها → دانلود پروژه → نصب
#  پایتون و Playwright/Chromium → noVNC → Nginx → گواهی SSL (Let's Encrypt یا
#  self-signed) → سرویس systemd → اجرا. قابل اجرای مجدد (خودترمیمی/Idempotent).
#
#  نمونهٔ استفاده:
#    curl -fsSL https://raw.githubusercontent.com/khajavy8056/Marketing-/main/server/install.sh | sudo bash -s -- --domain panel.example.com --email you@example.com
#
#  گزینه‌ها:
#    --domain  DOMAIN   دامنه برای SSL (اختیاری؛ بدون آن self-signed)
#    --email   EMAIL    ایمیل برای Let's Encrypt (اختیاری)
#    --dir     DIR      مسیر نصب (پیش‌فرض /opt/divar-server)
#    --repo    URL      آدرس مخزن (پیش‌فرض github khajavy8056/Marketing-)
#    --branch  BRANCH   شاخه (پیش‌فرض main)
#    --port    PORT     پورت داخلی برنامه (پیش‌فرض 8642)
#    --no-upgrade       سرور آپدیت/آپگرید نشود
# =============================================================================
set -euo pipefail

# ---------------------------- مقادیر پیش‌فرض --------------------------------
DOMAIN="${DOMAIN:-}"
EMAIL="${EMAIL:-}"
INSTALL_DIR="${INSTALL_DIR:-/opt/divar-server}"
REPO_URL="${REPO_URL:-https://github.com/khajavy8056/Marketing-.git}"
BRANCH="${BRANCH:-main}"
PORT="${PORT:-8642}"
DO_UPGRADE=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --email) EMAIL="$2"; shift 2 ;;
    --dir) INSTALL_DIR="$2"; shift 2 ;;
    --repo) REPO_URL="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --no-upgrade) DO_UPGRADE=0; shift ;;
    *) echo "گزینهٔ ناشناخته: $1" >&2; exit 2 ;;
  esac
done

# ------------------------------ ابزار نمایش --------------------------------
C_R="\033[0;31m"; C_G="\033[0;32m"; C_Y="\033[0;33m"; C_B="\033[0;34m"; C_N="\033[0m"
TOTAL_STEPS=12
STEP=0

bar() {  # bar <percent>
  local p=$1 w=40 f=$(( p * w / 100 )) e=$(( w - f )) i
  printf "\r["
  for ((i=0;i<f;i++)); do printf "█"; done
  for ((i=0;i<e;i++)); do printf "░"; done
  printf "] %3d%%" "$p"
}

step() {  # step <توضیح>
  STEP=$((STEP+1))
  local p=$(( STEP * 100 / TOTAL_STEPS ))
  printf "\n${C_B}▶ %s${C_N}\n" "$1"
  bar "$p"
  printf "\n"
}

die() { printf "\n${C_R}✗ خطا: %s${C_N}\n" "$1" >&2; exit 1; }
ok() { printf "${C_G}✓ %s${C_N}\n" "$1"; }

# ------------------------------- پیش‌شرط‌ها --------------------------------
if [[ $EUID -ne 0 ]]; then
  echo "برای نصب، دسترسی root لازم است. با sudo اجرا کنید:" >&2
  echo "  curl -fsSL ... | sudo bash -s -- --domain example.com" >&2
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  die "این نصب‌کننده فقط روی Debian/Ubuntu کار می‌کند (apt-get پیدا نشد)."
fi

export DEBIAN_FRONTEND=noninteractive

step "آپدیت و آپگرید سرور"
if [[ "$DO_UPGRADE" == "1" ]]; then
  apt-get update -y -qq >/dev/null || die "apt-get update ناموفق بود"
  apt-get upgrade -y -qq >/dev/null || die "apt-get upgrade ناموفق بود"
  ok "سرور به‌روز شد"
else
  ok "آپگرید رد شد (--no-upgrade)"
fi

step "نصب پیش‌نیازهای سیستم"
apt-get install -y -qq \
  git curl wget ca-certificates gnupg lsb-release \
  python3 python3-venv python3-pip \
  build-essential libssl-dev libffi-dev \
  xvfb x11vnc websockify \
  nginx certbot python3-certbot-nginx \
  fonts-dejavu-core >/dev/null || die "نصب پیش‌نیازها ناموفق بود"
ok "ابزارهای سیستم نصب شد (xvfb, x11vnc, websockify, nginx, certbot)"

step "دریافت پروژه از مخزن"
if [[ -d "$INSTALL_DIR/.git" ]]; then
  git -C "$INSTALL_DIR" fetch --all --quiet
  git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH" --quiet || true
  ok "پروژه به‌روزرسانی شد (خودترمیمی)"
else
  mkdir -p "$INSTALL_DIR"
  git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR" >/dev/null 2>&1 \
    || git clone --depth 1 "$REPO_URL" "$INSTALL_DIR" >/dev/null 2>&1 \
    || die "دانلود مخزن ناموفق بود — آدرس/شاخه را چک کنید"
  ok "پروژه کلون شد"
fi

step "ساخت محیط مجازی پایتون و نصب وابستگی‌ها"
python3 -m venv "$INSTALL_DIR/venv" || die "ساخت venv ناموفق بود"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip setuptools wheel
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/server/requirements.txt"
ok "وابستگی‌های پایتون نصب شد"

step "نصب مرورگر Chromium برای Playwright (headful + headless)"
"$INSTALL_DIR/venv/bin/playwright" install --with-deps chromium >/dev/null 2>&1 \
  || "$INSTALL_DIR/venv/bin/playwright" install chromium >/dev/null 2>&1 \
  || die "نصب Chromium ناموفق بود"
ok "Chromium نصب شد"

step "دریافت noVNC (کلاینت HTML5 مرورگر)"
if [[ ! -d "$INSTALL_DIR/novnc" ]]; then
  git clone --depth 1 https://github.com/novnc/noVNC.git "$INSTALL_DIR/novnc" >/dev/null 2>&1 \
    || die "دانلود noVNC ناموفق بود"
fi
ok "noVNC آماده شد"

step "ساخت کاربر و سرویس systemd"
if ! id -u divar >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin divar
fi
chown -R divar:divar "$INSTALL_DIR"
mkdir -p /var/www/certbot
sed -e "s|DIVAR_SERVER_PORT=8642|DIVAR_SERVER_PORT=$PORT|" \
    "$INSTALL_DIR/server/divar-server.service" > /etc/systemd/system/divar-server.service
systemctl daemon-reload
systemctl enable divar-server >/dev/null 2>&1 || true
ok "سرویس divar-server ثبت شد"

step "پیکربندی Nginx"
SERVER_NAME="${DOMAIN:-_}"
if [[ -n "$DOMAIN" ]]; then
  SSL_CERT="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
  SSL_KEY="/etc/letsencrypt/live/$DOMAIN/privkey.pem"
else
  SSL_CERT="/etc/ssl/certs/divar-selfsigned.crt"
  SSL_KEY="/etc/ssl/private/divar-selfsigned.key"
fi
sed -e "s|{{SERVER_NAME}}|$SERVER_NAME|g" \
    -e "s|{{SSL_CERT}}|$SSL_CERT|g" \
    -e "s|{{SSL_KEY}}|$SSL_KEY|g" \
    "$INSTALL_DIR/server/nginx/divar.conf.template" > /etc/nginx/sites-available/divar
ln -sf /etc/nginx/sites-available/divar /etc/nginx/sites-enabled/divar
rm -f /etc/nginx/sites-enabled/default
nginx -t >/dev/null 2>&1 || die "پیکربندی Nginx خطا دارد"
ok "Nginx پیکربندی شد"

_selfsigned() {
  if [[ ! -f /etc/ssl/certs/divar-selfsigned.crt ]]; then
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
      -keyout /etc/ssl/private/divar-selfsigned.key \
      -out /etc/ssl/certs/divar-selfsigned.crt \
      -subj "/CN=${DOMAIN:-divar-server}" >/dev/null 2>&1 || true
  fi
  echo "  ⚠ بدون دامنه: گواهی self-signed ساخته شد (بعداً با --domain تمدید کنید)"
}

step "گواهی SSL"
if [[ -n "$DOMAIN" && -n "$EMAIL" ]]; then
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" \
    --redirect --keep-until-expiring >/dev/null 2>&1 \
    || echo "  ⚠ certbot ناموفق؛ گواهی self-signed جایگزین می‌شود"
  if [[ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]]; then
    ok "گواهی Let's Encrypt (۹۰ روزه، تمدید خودکار) نصب شد"
  else
    _selfsigned
  fi
else
  _selfsigned
fi

step "راه‌اندازی مجدد Nginx و سرویس"
systemctl restart nginx
systemctl restart divar-server || true
ok "سرویس‌ها راه‌اندازی شدند"

# ------------------------------- پایان ------------------------------------
bar 100
printf "\n\n${C_G}══════════════════════════════════════════════════════${C_N}\n"
echo "  نصب کامل شد ✅"
echo "  پوشهٔ نصب:      $INSTALL_DIR"
echo "  پورت داخلی:     $PORT (فقط از طریق Nginx در دسترس است)"
if [[ -n "$DOMAIN" ]]; then
  echo "  آدرس پنل:       https://$DOMAIN"
else
  echo "  آدرس پنل:       http://SERVER_IP  (یا https با self-signed)"
fi
echo "  ورود پیش‌فرض:   admin / admin  (در اولین ورود تغییر رمز الزامی است)"
echo "  لاگ:            journalctl -u divar-server -f"
echo "  اجرای مجدد:     sudo bash $INSTALL_DIR/server/install.sh"
echo "${C_G}══════════════════════════════════════════════════════${C_N}"
exit 0
