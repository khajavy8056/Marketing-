# -*- coding: utf-8 -*-
"""🧠 تیرا — نصب‌کننده هوشمند مستقل

- مدل Qwen با DownloadManager استاندارد (resume + آینه) دانلود و نصب می‌شود
- اگر مدل نباشد خودکار نصب می‌کند
- اتصالات سیستم: پوشه‌ها، config، DB، فایروال، میانبر
- پنل اصلی: پنجره native بدون مرورگر (pywebview)
- فایل قابل نصب: python tira_installer.py یا exe

استفاده:
  python installer/tira_installer.py --dest ~/DivarMarketing
  python installer/tira_installer.py --cli
"""

from __future__ import annotations

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path

# اضافه کردن root به sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

APP_ID = "DivarMarketing"
VERSION = "3.4.0-tira-desktop"

def log(msg: str):
    print(msg, flush=True)

def ensure_dirs(base: Path):
    for sub in ("accounts", "logs", "app-chromium", "nlu-model", "nlu-download", "data"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    # همچنین پوشه پایدار کاربر
    try:
        from marketing_divar.paths import user_data_dir
        ud = user_data_dir()
        for sub in ("accounts", "logs", "app-chromium", "nlu-model", "nlu-download"):
            (ud / sub).mkdir(parents=True, exist_ok=True)
        return ud
    except Exception:
        return base

def install_chromium():
    log("🌐 Checking Chromium (DownloadManager)...")
    try:
        from marketing_divar.app_chromium import is_ready, ensure_installed, status
        if is_ready():
            log(f"✅ Chromium ready: {status()}")
            return True
        log("📥 Downloading Chromium with DownloadManager...")
        path = ensure_installed(log=log, progress=lambda p: log(f"Chromium {p}%"))
        log(f"✅ Chromium installed: {path}")
        return True
    except Exception as e:
        log(f"⚠️ Chromium install failed (will retry in panel): {e}")
        return False

def install_nlu_model():
    log("🧠 Checking Tira model (Qwen) with DownloadManager...")
    try:
        from marketing_divar.nlu_model import is_ready, ensure_installed, status, backend_name
        if is_ready():
            st = status()
            log(f"✅ Tira model ready: {st.get('path')} backend={backend_name()}")
            return True
        log("📥 Downloading Tira model with DownloadManager (resume + mirrors)...")
        # از DownloadManager استاندارد استفاده می‌کند (داخل nlu_model)
        path = ensure_installed(log=log, progress=lambda p: log(f"Tira model {p}%"))
        log(f"✅ Tira model installed: {path} backend={backend_name()}")
        return True
    except Exception as e:
        log(f"⚠️ Tira model download failed (fallback active): {e}")
        # حتی اگر دانلود نشد، fallback هوشمند کار می‌کند
        try:
            from marketing_divar.nlu_model import status
            log(f"ℹ️ Status: {status()}")
        except Exception:
            pass
        return False

def install_pywebview():
    log("🖥️ Checking pywebview (native window)...")
    try:
        import webview
        log(f"✅ pywebview ready: {webview.__version__ if hasattr(webview, '__version__') else 'ok'}")
        return True
    except ImportError:
        log("📦 Installing pywebview...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "pywebview", "-q"], check=False, timeout=60)
            import webview
            log("✅ pywebview installed")
            return True
        except Exception as e:
            log(f"⚠️ pywebview install failed (Chromium fallback will be used): {e}")
            return False

def create_config(data_dir: Path):
    cfg_path = data_dir / "config.json"
    if cfg_path.exists():
        log(f"⚙️ Config exists: {cfg_path}")
        return
    cfg = {
        "version": VERSION,
        "ai_name": "تیرا",
        "ai_subtitle": "دستیار شکار حرفه‌ای",
        "platform_divar": True,
        "platform_sheypoor": True,
        "platform_ring": False,
        "per_account_daily_limit": 60,
        "ip_daily_limit": 240,
        "phone_delay_sec": 45,
        "scan_interval_sec": 300,
        "vip_enabled": True,
        "hunter_enabled": True,
        "desktop_mode": True,
    }
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"⚙️ Config created: {cfg_path}")

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Tira Desktop Installer")
    ap.add_argument("--dest", default="", help="Install destination")
    ap.add_argument("--cli", action="store_true", help="CLI mode")
    args = ap.parse_args()

    if args.dest:
        dest = Path(args.dest).expanduser().resolve()
    else:
        try:
            from marketing_divar.paths import user_data_dir
            dest = user_data_dir()
        except Exception:
            dest = Path.home() / "DivarMarketing"

    dest.mkdir(parents=True, exist_ok=True)
    log(f"📁 Install dir: {dest}")
    ud = ensure_dirs(dest)
    create_config(ud)

    # اتصالات سیستم
    if sys.platform == "win32":
        try:
            cmd = ["netsh", "advfirewall", "firewall", "add", "rule",
                   f"name=Divar Marketing", "dir=in", "action=allow",
                   "protocol=TCP", f"localport=8642"]
            subprocess.run(cmd, capture_output=True, timeout=10)
            log("🔥 Firewall rule added")
        except Exception as e:
            log(f"Firewall skip: {e}")

    # وابستگی‌ها با DownloadManager
    install_pywebview()
    install_chromium()
    install_nlu_model()

    log("")
    log("✅ Tira Desktop installation complete!")
    log(f"📁 Data: {ud}")
    log(f"🧠 Model: {ud / 'nlu-model'}")
    log(f"🌐 Chromium: {ud / 'app-chromium'}")
    log("")
    log("🚀 Run: python main.py --desktop")
    log("   or:  python -m marketing_divar.desktop_app")
    log("")
    # اگر cli نیست، سعی کن دسکتاپ را باز کنی
    if not args.cli:
        try:
            from marketing_divar.desktop_app import main as desktop_main
            log("🖥️ Opening Tira Desktop window...")
            desktop_main()
        except Exception as e:
            log(f"Could not open desktop automatically: {e}")
            log("Run manually: python main.py --desktop")

if __name__ == "__main__":
    main()
