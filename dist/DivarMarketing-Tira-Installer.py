#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""🧠 تیرا — نصب‌کننده خودکار با DownloadManager استاندارد
این فایل را دانلود و اجرا کنید:
  python DivarMarketing-Tira-Installer.py

- پوشه داده پایدار می‌سازد
- Chromium با DownloadManager (resume + mirrors) دانلود می‌کند
- مدل Qwen تیرا با DownloadManager خودکار نصب می‌کند (اگر نباشد)
- اتصالات سیستم (فایروال، کانفیگ، DB) را کامل می‌کند
- در آخر پنجره دسکتاپ مستقل بدون مرورگر باز می‌شود
"""
import os, sys, json, shutil, subprocess, threading, time
from pathlib import Path

print("🧠 تیرا — نصب‌کننده هوشمند")
print("📥 در حال آماده‌سازی...")

# اگر در پوشه سورس هستیم، مستقیم از همان استفاده کن
ROOT_CANDIDATES = [
    Path(__file__).resolve().parent,
    Path.cwd(),
]
for rc in ROOT_CANDIDATES:
    if (rc / "marketing_divar" / "desktop_app.py").exists():
        sys.path.insert(0, str(rc))
        break

try:
    from marketing_divar.paths import user_data_dir, apply_runtime_paths
    data_dir = user_data_dir()
    apply_runtime_paths()
except Exception:
    data_dir = Path.home() / "DivarMarketing" if os.name != "nt" else Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "DivarMarketing"
    data_dir.mkdir(parents=True, exist_ok=True)

print(f"📁 Data dir: {data_dir}")

# نصب وابستگی‌های پایه
def pip_install(pkg):
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", pkg, "-q", "--disable-pip-version-check"], timeout=90)
        return True
    except Exception:
        return False

# pywebview
try:
    import webview
    print("✅ pywebview ready")
except ImportError:
    print("📦 Installing pywebview for native window...")
    pip_install("pywebview")

# fastapi, uvicorn, etc
for pkg in ["fastapi", "uvicorn", "requests", "tqdm"]:
    try:
        __import__(pkg)
    except ImportError:
        print(f"📦 Installing {pkg}...")
        pip_install(pkg)

# حالا چک Chromium و مدل
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    # اگر marketing_divar نیست، سعی کن دانلود کنی
    import marketing_divar
    from marketing_divar.app_chromium import is_ready as chrome_ready, ensure_installed as chrome_install
    from marketing_divar.nlu_model import is_ready as nlu_ready, ensure_installed as nlu_install

    if not chrome_ready():
        print("📥 Downloading Chromium with DownloadManager (resume)...")
        try:
            chrome_install(log=print, progress=lambda p: print(f"Chromium {p}%"))
            print("✅ Chromium ready")
        except Exception as e:
            print(f"⚠️ Chromium will retry in panel: {e}")
    else:
        print("✅ Chromium ready")

    if not nlu_ready():
        print("📥 Downloading Tira model (Qwen) with DownloadManager...")
        try:
            nlu_install(log=print, progress=lambda p: print(f"Tira {p}%"))
            print("✅ Tira model ready")
        except Exception as e:
            print(f"⚠️ Tira model fallback active: {e}")
    else:
        print("✅ Tira model ready")

    # اجرای دسکتاپ
    print("🚀 Opening Tira Desktop (native window, no browser)...")
    from marketing_divar.desktop_app import main as desktop_main
    desktop_main()

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback; traceback.print_exc()
    print("")
    print("If you are not in source folder, download full zip from Releases:")
    print("https://github.com/khajavy8056/Marketing-/releases")
    print("Then run: python main.py --desktop")

