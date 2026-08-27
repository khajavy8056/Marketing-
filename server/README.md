# 🖥️ نسخهٔ سرور لینوکسی «مارکتینگ دیوار»

این پوشه نسخهٔ **مستقل و جدا** از نسخهٔ ویندوزی است. هیچ تداخلی با فایل‌های
ویندوز (`marketing_divar/` در ریشهٔ مخزن) ندارد و فقط روی **سرور لینوکس**
نصب/اجرا می‌شود. هستهٔ جمع‌آوری سرنخ را بازمصرف می‌کند و سه لایهٔ جدید اضافه می‌کند:

1. **احراز هویت** — صفحهٔ لاگین قبل از پنل؛ پیش‌فرض `admin/admin` + اجبار تغییر رمز در اولین ورود.
2. **نشست ریموت پروفایل** — مدیریت مرورگر Chromium روی سرور (Xvfb + x11vnc + noVNC) برای لاگین اولیه و حل دستی کپچا از راه دور.
3. **نصب یک‌دستوری** — از صفر تا صد (آپدیت سرور، پیش‌نیازها، SSL، Nginx، systemd).

---

## 📥 نصب (یک دستور)

```bash
curl -fsSL https://raw.githubusercontent.com/khajavy8056/Marketing-/main/server/install.sh \
  | sudo bash -s -- --domain panel.example.com --email you@example.com
```

بدون دامنه (فقط IP، گواهی self-signed):

```bash
curl -fsSL https://raw.githubusercontent.com/khajavy8056/Marketing-/main/server/install.sh \
  | sudo bash -s --
```

### گزینه‌ها

| گزینه | پیش‌فرض | توضیح |
|---|---|---|
| `--domain` | — | دامنه برای گواهی Let's Encrypt (۹۰ روزه، تمدید خودکار) |
| `--email` | — | ایمیل برای Let's Encrypt |
| `--dir` | `/opt/divar-server` | مسیر نصب |
| `--repo` | `github.com/khajavy8056/Marketing-` | آدرس مخزن |
| `--branch` | `main` | شاخه |
| `--port` | `8642` | پورت داخلی برنامه (فقط از طریق Nginx در دسترس) |
| `--no-upgrade` | — | سرور آپدیت/آپگرید نشود |

نصب‌کننده **قابل اجرای مجدد (خودترمیمی)** است: اگر وسط کار قطع شد یا خواستید
به‌روزرسانی کنید، همان دستور را دوباره بزنید — پروژه `git pull` می‌شود و همه‌چیز
از نو ساخته می‌شود.

### بعد از نصب
- پنل: `https://DOMAIN` یا `http://SERVER_IP`
- ورود پیش‌فرض: `admin / admin` → در اولین ورود **تغییر رمز الزامی** است.
- لاگ سرویس: `journalctl -u divar-server -f`
- حذف: `sudo bash /opt/divar-server/server/uninstall.sh`

---

## 🧩 پروفایل‌های ریموت (لاگین / کپچا از راه دور)

در نسخهٔ ویندوز، هر اکانت یک پنجرهٔ Chromium بومی باز می‌کرد. روی سرور بدون
صفحه‌نمایش، همان پروفایل (`accounts/<name>/chromium/`) روی یک **صفحه‌نمایش مجازی**
اجرا و تصویرش از طریق **noVNC** داخل مرورگر خودِ اپراتور نمایش داده می‌شود:

```
مرورگر اپراتور ──https──▶ Nginx ──▶ برنامه (احراز هویت) ──ws──▶ websockify
      ──▶ x11vnc ──▶ Xvfb :N ──▶ Chromium headful (user_data_dir همان اکانت)
```

- در تب «اکانت‌ها» کارت **«پروفایل‌های ریموت»** اضافه می‌شود:
  - **«باز کردن پروفایل»** → نشست زنده باز و تب noVNC باز می‌شود.
  - **«بستن نشست»** → مرورگر/پردازش‌ها بسته می‌شوند، ولی **پوشهٔ پروفایل روی دیسک می‌ماند** (کوکی/لاگین حفظ می‌شود).
  - **«کپچا حل شد / ادامه»** → وضعیت اکانت را تأیید و مانیتور را از سر می‌گیرد.
- **هیچ حل خودکار کپچایی وجود ندارد** — فقط «دیدن و کنترل از راه دور».

### چرخهٔ عمر
- **بسته (پیش‌فرض):** هیچ Xvfb/x11vnc/Chromium اجرا نیست؛ فقط پوشهٔ پروفایل روی دیسک.
- **باز:** یک شمارهٔ نمایش (`:100` تا `:199`) + پورت VNC + پورت websockify اشغال می‌شود.
- **بستن:** همه آزاد می‌شود؛ پروفایل دست‌نخورده می‌ماند.
- نشست‌های بی‌کار بعد از ۱۰ دقیقه خودکار بسته می‌شوند.

### امنیت
- `x11vnc` و `websockify` فقط روی `127.0.0.1` گوش می‌دهند؛ **هیچ پورت عمومی باز نمی‌شود**.
- تنها ورود، مسیر `/remote/.../ws` پشت احراز هویت پنل است.
- در ری‌استارت، `cleanup_orphans()` پردازش‌های یتیم را پاک می‌کند.

---

## 📁 ساختار پوشه

```
server/
├── README.md                 این سند
├── install.sh                نصب‌کنندهٔ یک‌دستوری (خودترمیمی)
├── uninstall.sh              حذف کامل
├── requirements.txt          وابستگی‌های سرور
├── divar-server.service      واحد systemd
├── nginx/divar.conf.template پیکربندی Nginx
├── scripts/build_static.py   تولید index.html سرور از روی index.html ویندوز
├── divar_server/
│   ├── __init__.py           نسخه
│   ├── __main__.py           نقطهٔ ورود (uvicorn بدون پنجرهٔ بومی)
│   ├── app.py                ساخت app: احراز + هسته + ریموت
│   ├── auth.py               لاگین / نشست / تغییر رمز (PBKDF2)
│   ├── remote_session.py     Xvfb + x11vnc + websockify + Playwright
│   ├── remote_router.py      endpoint ها + پل WebSocket noVNC
│   └── static/
│       ├── login.html        صفحهٔ ورود + تغییر رمز
│       └── index.html        پنل (ساخته‌شده توسط build_static.py)
└── tests/                    تست‌های احراز و نشست ریموت
```

## 🧪 اجرای محلی (بدون نصب کامل، برای توسعه)

```bash
cd server
python3 -m venv .venv && .venv/bin/pip install -r ../requirements.txt -r requirements.txt
DIVAR_DATA_DIR=/tmp/divar-dev DIVAR_SERVER_PORT=8642 .venv/bin/python -m divar_server
```

برای تست بدون X واقعی (شبیه‌سازی):

```bash
DIVAR_SERVER_NO_VNC=1 python3 -m unittest discover -s tests
```

---

## 🔄 نقشهٔ راه (فازهای سند فنی)

| فاز | وضعیت |
|---|---|
| ۰ — زیرساخت سرور (xvfb/x11vnc/websockify/noVNC/nginx) | ✅ در `install.sh` |
| ۱ — ماژول `remote_session.py` | ✅ |
| ۲ — endpoint های FastAPI + پل WS | ✅ |
| ۳ — رابط کاربری (کارت پروفایل‌های ریموت) | ✅ تزریق در `build_static.py` |
| ۴ — دکمهٔ «کپچا حل شد» | ✅ (`remoteVerify` → `captcha-cleared`) |
| ۵ — اتصال به هشدار تلگرام با لینک مستقیم | 🔜 بعد از استقرار (لینک `/remote/...` در پیام تلگرام) |
| ۶ — سخت‌سازی (timeout، پاکسازی یتیم، سقف نشست) | ✅ timeout + cleanup + `MAX_SESSIONS=100` |
