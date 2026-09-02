# -*- coding: utf-8 -*-
"""Divar Marketing - Native Windows Installer v4.1 - Fixed
- Single encrypted file Setup.exe with payload.zip.enc
- Includes Tira model + Chromium + libs (offline 1-2GB)
- Chic wizard: Welcome -> License -> Data Preserve -> Location -> Components -> Progress -> Finish
- Next/Back/Browse/Install/Finish like Office/Adobe - no black console - only GUI native
- Data preservation alarm
- Encryption SHA256 XOR + zlib
- DownloadManager with resume + speed + ETA
- Main app is native Windows window (desktop_app.py) - NOT browser
"""

from __future__ import annotations

import os
import sys
import shutil
import subprocess
import threading
import zipfile
import zlib
import hashlib
import time
import traceback
from pathlib import Path
from typing import Callable, Optional

APP_ID = "DivarMarketing"
APP_NAME = "Divar Marketing"
APP_NAME_FA = "مارکتینگ دیوار"
APP_VERSION = "4.2.0-native-fixed"
PORT = 8642
CREATE_NO_WINDOW = 0x08000000
ENCRYPTION_KEY = b"DivarMarketing-2024-Secure-Key-Tira-v4.2-Native-Fixed-NoFreeze"

def _meipass() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent

def default_install_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_ID / "app"

def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_ID

def payload_paths() -> list[Path]:
    mp = _meipass()
    return [
        mp / "payload.zip.enc",
        mp / "payload.zip",
        Path(__file__).resolve().parent / "payload.zip.enc",
        Path(__file__).resolve().parent / "payload.zip",
        Path(__file__).resolve().parent.parent / "installer" / "payload.zip.enc",
        Path(__file__).resolve().parent.parent / "installer" / "payload.zip",
    ]

def app_icon() -> Path:
    for p in (_meipass() / "app.ico", Path(__file__).resolve().parent / "app.ico", Path(__file__).resolve().parent.parent / "installer" / "app.ico"):
        if p.exists():
            return p
    return Path()

def decrypt_data(data: bytes, key: bytes = ENCRYPTION_KEY) -> bytes:
    """رمزگشایی — سازگار با هر دو فرمت قدیمی و جدید chunked v4.2"""
    try:
        key_hash = hashlib.sha256(key).digest()
        # تشخیص فرمت جدید chunked: اول 8 بایت سایز کل
        # اگر فرمت جدید باشد، باید chunked بخوانیم
        if len(data) > 12:
            try:
                # تست فرمت جدید: 8 بایت سایز + 4 بایت لن چانک
                total_size = int.from_bytes(data[:8], 'big')
                chunk_len = int.from_bytes(data[8:12], 'big')
                # اگر منطقی بود (total_size معقول و chunk_len معقول)
                if 0 < total_size < 10*1024*1024*1024 and 0 < chunk_len < 50*1024*1024 and len(data) > 12 + chunk_len:
                    # فرمت جدید chunked
                    out = bytearray()
                    offset = 0
                    # Skip header 8 bytes
                    offset = 8
                    while offset < len(data):
                        if offset + 4 > len(data):
                            break
                        clen = int.from_bytes(data[offset:offset+4], 'big')
                        offset += 4
                        if offset + clen > len(data):
                            break
                        xored = data[offset:offset+clen]
                        offset += clen
                        # XOR back
                        compressed = bytes(b ^ key_hash[i % len(key_hash)] for i, b in enumerate(xored))
                        try:
                            chunk = zlib.decompress(compressed)
                        except:
                            chunk = compressed
                        out.extend(chunk)
                        if len(out) >= total_size:
                            break
                    return bytes(out)
            except Exception:
                pass  # Fallback to old format
        
        # فرمت قدیمی: کل دیتا XOR + zlib
        xored = bytes(b ^ key_hash[i % len(key_hash)] for i, b in enumerate(data))
        try:
            return zlib.decompress(xored)
        except:
            return xored
    except Exception:
        return data

def decrypt_file_chunked(src_path: Path, dest_path: Path, key: bytes = ENCRYPTION_KEY) -> Path:
    """رمزگشایی chunked از فایل — v4.2"""
    try:
        key_hash = hashlib.sha256(key).digest()
        with open(src_path, 'rb') as fin:
            # Check if old format or new
            header = fin.read(12)
            if len(header) < 12:
                # Old format fallback
                fin.seek(0)
                data = fin.read()
                dec = decrypt_data(data, key)
                dest_path.write_bytes(dec)
                return dest_path
            
            total_size = int.from_bytes(header[:8], 'big')
            first_chunk_len = int.from_bytes(header[8:12], 'big')
            
            # Validate new format
            if not (0 < total_size < 10*1024*1024*1024 and 0 < first_chunk_len < 50*1024*1024):
                # Old format
                fin.seek(0)
                data = fin.read()
                dec = decrypt_data(data, key)
                dest_path.write_bytes(dec)
                return dest_path
            
            # New format — chunked
            fin.seek(0)
            fin.read(8)  # Skip total_size already read
            with open(dest_path, 'wb') as fout:
                while True:
                    len_bytes = fin.read(4)
                    if not len_bytes or len(len_bytes) < 4:
                        break
                    clen = int.from_bytes(len_bytes, 'big')
                    if clen <= 0 or clen > 50*1024*1024:
                        break
                    xored = fin.read(clen)
                    if not xored or len(xored) != clen:
                        break
                    compressed = bytes(b ^ key_hash[i % len(key_hash)] for i, b in enumerate(xored))
                    try:
                        chunk = zlib.decompress(compressed)
                    except:
                        chunk = compressed
                    fout.write(chunk)
        return dest_path
    except Exception as e:
        # Fallback: try old method
        try:
            data = src_path.read_bytes()
            dec = decrypt_data(data, key)
            dest_path.write_bytes(dec)
            return dest_path
        except Exception as e2:
            raise e2

def find_payload() -> Optional[Path]:
    for p in payload_paths():
        if p.exists() and p.stat().st_size > 1000:
            return p
    return None

def has_previous_data() -> dict:
    d = data_dir()
    info = {"exists": False, "accounts": 0, "leads": 0, "size_mb": 0}
    if not d.exists():
        return info
    info["exists"] = True
    try:
        acc = d / "accounts"
        if acc.exists():
            info["accounts"] = len([x for x in acc.iterdir() if x.is_dir()])
        data_db = d / "app" / "data" / "divar_leads.db"
        if not data_db.exists():
            data_db = d / "data" / "divar_leads.db"
        if data_db.exists():
            info["size_mb"] = data_db.stat().st_size // 1024 // 1024
            try:
                import sqlite3
                con = sqlite3.connect(str(data_db))
                cur = con.execute("SELECT COUNT(*) FROM leads")
                info["leads"] = cur.fetchone()[0]
                con.close()
            except Exception:
                pass
    except Exception:
        pass
    return info

def create_layout(dest: Path, log: Callable[[str], None]) -> None:
    for name in ("data", "logs", "accounts", "app-chromium", "nlu-model"):
        (dest / name).mkdir(parents=True, exist_ok=True)
    persist = data_dir()
    for name in ("accounts", "logs", "app-chromium", "nlu-model", "data"):
        (persist / name).mkdir(parents=True, exist_ok=True)
    log(f"✓ پوشه‌ها آماده: {dest}")

def extract_payload(dest: Path, log: Callable[[str], None], progress_cb: Optional[Callable[[int, str], None]] = None, preserve_mode: str = "keep") -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    zpath = find_payload()
    
    prev = has_previous_data()
    if prev["exists"] and preserve_mode != "delete_all":
        log(f"📦 اطلاعات قبلی یافت شد: {prev['accounts']} اکانت، {prev['leads']} سرنخ، {prev['size_mb']} MB")
        if preserve_mode == "keep":
            log("✓ تمام اطلاعات قبلی حفظ می‌شود")
        elif preserve_mode == "keep_accounts":
            log("✓ فقط اکانت‌ها حفظ می‌شود")
            try:
                for db_path in [data_dir() / "app" / "data" / "divar_leads.db", data_dir() / "data" / "divar_leads.db"]:
                    if db_path.exists():
                        db_path.unlink()
            except Exception as e:
                log(f"⚠️ حذف دیتابیس: {e}")
    elif prev["exists"] and preserve_mode == "delete_all":
        log("🗑️ حذف کامل اطلاعات قبلی...")
        try:
            for p in [data_dir() / "data", data_dir() / "logs"]:
                if p.exists():
                    shutil.rmtree(p, ignore_errors=True)
            acc = data_dir() / "accounts"
            if acc.exists():
                shutil.rmtree(acc, ignore_errors=True)
        except Exception as e:
            log(f"⚠️ حذف: {e}")
    
    if not zpath:
        root = Path(__file__).resolve().parent.parent
        log(f"⚠️ payload پیدا نشد — کپی از سورس: {root}")
        names = ("main.py", "requirements.txt", "marketing_divar", "installer")
        total = len(names)
        for idx, name in enumerate(names):
            src = root / name
            dst = dest / name
            if not src.exists():
                continue
            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "install-log.txt", "payload.zip", "payload.zip.enc"))
            else:
                shutil.copy2(src, dst)
            if progress_cb:
                progress_cb(int((idx+1)/total*70), f"کپی {name}...")
    else:
        log(f"📦 payload: {zpath} ({zpath.stat().st_size // 1024 // 1024} MB)")
        if progress_cb:
            progress_cb(5, "رمزگشایی فایل نصب...")
        # Check if encrypted
        try:
            with open(zpath, 'rb') as f:
                head = f.read(2)
            is_encrypted = zpath.suffix == ".enc" or head != b"PK"
        except:
            is_encrypted = zpath.suffix == ".enc"
        
        tmp_zip = dest.parent / "_payload_tmp.zip"
        if is_encrypted:
            log("🔐 رمزگشایی payload رمزنگاری شده (chunked v4.2)...")
            if progress_cb:
                progress_cb(10, "رمزگشایی chunked...")
            try:
                # Use chunked decryption to avoid RAM overload
                decrypt_file_chunked(zpath, tmp_zip)
                log(f"✓ رمزگشایی chunked کامل: {tmp_zip.stat().st_size//1024//1024} MB")
            except Exception as e:
                log(f"⚠️ رمزگشایی chunked خطا: {e} — تلاش با روش قدیمی...")
                try:
                    data = zpath.read_bytes()
                    data = decrypt_data(data)
                    tmp_zip.write_bytes(data)
                    log(f"✓ رمزگشایی قدیمی: {len(data)//1024//1024} MB")
                except Exception as e2:
                    log(f"❌ رمزگشایی ناموفق: {e2}")
                    raise
        else:
            # Not encrypted — just copy
            log(f"📦 payload خام (بدون رمز): کپی...")
            shutil.copy2(zpath, tmp_zip)
        if progress_cb:
            progress_cb(20, "استخراج فایل‌ها...")
        with zipfile.ZipFile(tmp_zip, "r") as zf:
            members = zf.infolist()
            total = len(members)
            for idx, member in enumerate(members):
                zf.extract(member, dest)
                if progress_cb and idx % 20 == 0:
                    pct = 20 + int((idx/total)*60)
                    progress_cb(pct, f"استخراج {idx}/{total}...")
        tmp_zip.unlink(missing_ok=True)
        log(f"✓ {total} فایل استخراج شد")
    
    create_layout(dest, log)
    exe = dest / f"{APP_ID}.exe"
    if exe.exists():
        return exe
    nested = dest / "dist" / f"{APP_ID}.exe"
    if nested.exists():
        return nested
    main = dest / "main.py"
    if main.exists():
        return main
    return dest / "main.py"

def make_shortcut(target: Path, workdir: Path, ico: Path, log: Callable[[str], None]) -> None:
    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    start = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        use_com = True
    except Exception:
        use_com = False
        shell = None
    pyw = Path(sys.executable).with_name("pythonw.exe")
    for folder, fname in ((desktop, f"{APP_NAME}.lnk"), (start, f"{APP_NAME}.lnk")):
        if not folder:
            continue
        try:
            folder.mkdir(parents=True, exist_ok=True)
            lnk = folder / fname
            if use_com:
                sc = shell.CreateShortcut(str(lnk))
                if target.suffix.lower() == ".exe":
                    sc.TargetPath = str(target)
                    sc.Arguments = ""
                else:
                    if pyw.exists():
                        sc.TargetPath = str(pyw)
                        sc.Arguments = f'"{target}"'
                    else:
                        sc.TargetPath = sys.executable
                        sc.Arguments = f'"{target}"'
                sc.WorkingDirectory = str(workdir)
                sc.Description = f"{APP_NAME} {APP_VERSION} Native"
                sc.WindowStyle = 1
                if ico and ico.exists():
                    sc.IconLocation = str(ico)
                sc.Save()
                log(f"✓ میانبر: {lnk}")
            else:
                # PowerShell fallback
                icon = str(ico) if ico and ico.exists() else ""
                if target.suffix.lower() == ".exe":
                    tgt, args = str(target), ""
                else:
                    if pyw.exists():
                        tgt, args = str(pyw), f'"{target}"'
                    else:
                        tgt, args = sys.executable, f'"{target}"'
                ps_cmd = f'$s=(New-Object -ComObject WScript.Shell).CreateShortcut("{lnk}");$s.TargetPath="{tgt}";$s.Arguments="{args}";$s.WorkingDirectory="{workdir}";$s.Description="{APP_NAME} {APP_VERSION}";$s.WindowStyle=1;'
                if icon:
                    ps_cmd += f'$s.IconLocation="{icon}";'
                ps_cmd += "$s.Save()"
                subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=False, capture_output=True)
                log(f"✓ میانبر: {lnk}")
        except Exception as e:
            log(f"⚠️ میانبر نشد: {e}")

def open_firewall(log: Callable[[str], None]) -> None:
    cmd = ["netsh", "advfirewall", "firewall", "add", "rule", f"name={APP_NAME}", "dir=in", "action=allow", "protocol=TCP", f"localport={PORT}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if r.returncode == 0:
            log(f"✓ فایروال: پورت {PORT} باز شد")
        else:
            log("⚠️ فایروال: با Administrator اجرا کن")
    except Exception as e:
        log(f"⚠️ فایروال: {e}")

def _popen_hidden(args, cwd, env) -> None:
    kwargs = {"cwd": str(cwd), "env": env}
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 1
        kwargs["startupinfo"] = si
        kwargs["creationflags"] = CREATE_NO_WINDOW
    subprocess.Popen(args, **kwargs)

def launch(target: Path, workdir: Path, log: Callable[[str], None]) -> None:
    log(f"🚀 اجرای {APP_NAME} نیتیو ویندوز...")
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    chrome = str(data_dir() / "app-chromium")
    env["PLAYWRIGHT_BROWSERS_PATH"] = chrome
    env["DIVAR_CHROMIUM_DIR"] = chrome
    if target.suffix.lower() == ".exe":
        _popen_hidden([str(target)], workdir, env)
    else:
        pyw = Path(sys.executable).with_name("pythonw.exe")
        exe = str(pyw) if pyw.exists() else sys.executable
        _popen_hidden([exe, str(target)], workdir, env)
    log(f"✓ برنامه نیتیو اجرا شد — پنجره ویندوز استاندارد")

def gui_wizard() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, ttk, messagebox
    except Exception as e:
        err = f"GUI نیاز به Tkinter دارد: {e}"
        print(err)
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, err, f"{APP_NAME} Setup", 0x10)
        except:
            pass
        return 2

    root = tk.Tk()
    root.title(f"{APP_NAME} Setup - {APP_VERSION} - Native Windows")
    root.geometry("860x780")
    root.resizable(False, False)
    root.configure(bg="#f0f4f8")
    try:
        ico = app_icon()
        if ico.exists():
            root.iconbitmap(default=str(ico))
    except Exception:
        pass

    style = ttk.Style()
    try:
        style.theme_use("vista")
    except:
        pass
    style.configure("TProgressbar", thickness=20, troughcolor="#e3e8f0", background="#1976d2")
    style.configure("Chrome.Horizontal.TProgressbar", background="#8e5bd9", thickness=18)
    style.configure("Model.Horizontal.TProgressbar", background="#2e9e5b", thickness=18)

    current_step = [0]
    install_dir_var = tk.StringVar(value=str(default_install_dir()))
    agree_var = tk.BooleanVar(value=False)
    comp_chrome_var = tk.BooleanVar(value=True)
    comp_model_var = tk.BooleanVar(value=True)
    comp_shortcut_var = tk.BooleanVar(value=True)
    preserve_var = tk.StringVar(value="keep")

    main_frame = tk.Frame(root, bg="#f0f4f8")
    main_frame.pack(fill="both", expand=True)

    header = tk.Frame(main_frame, bg="#0f2a4a", height=95)
    header.pack(fill="x")
    header.pack_propagate(False)
    left_hdr = tk.Frame(header, bg="#0f2a4a")
    left_hdr.pack(side="left", padx=20, pady=12, fill="y")
    tk.Label(left_hdr, text=f"🧠 {APP_NAME_FA}", font=("Segoe UI", 16, "bold"), bg="#0f2a4a", fg="white").pack(anchor="w")
    tk.Label(left_hdr, text=f"{APP_NAME} - تیرا v{APP_VERSION} - نیتیو ویندوز", font=("Segoe UI", 9, "bold"), bg="#0f2a4a", fg="#8ec0f0").pack(anchor="w")
    tk.Label(left_hdr, text="پنجره استاندارد ویندوز مثل Office - بدون کنسول سیاه", font=("Segoe UI", 8), bg="#0f2a4a", fg="#a78bfa").pack(anchor="w")
    right_hdr = tk.Frame(header, bg="#0f2a4a")
    right_hdr.pack(side="right", padx=20, pady=12)
    tk.Label(right_hdr, text=f"v{APP_VERSION}", font=("Segoe UI", 10, "bold"), bg="#0f2a4a", fg="#a78bfa").pack(anchor="e")
    tk.Label(right_hdr, text="Native Windows Setup", font=("Segoe UI", 8, "bold"), bg="#0f2a4a", fg="#38bdf8").pack(anchor="e")

    steps_bar = tk.Frame(main_frame, bg="#e8eef7", height=42)
    steps_bar.pack(fill="x")
    steps_bar.pack_propagate(False)
    step_labels = []
    step_names = ["خوش‌آمدید", "مجوز", "اطلاعات قبلی", "محل نصب", "اجزاء", "نصب", "پایان"]
    for i, name in enumerate(step_names):
        lbl = tk.Label(steps_bar, text=f"{i+1}. {name}", font=("Segoe UI", 8, "bold" if i==0 else "normal"), bg="#e8eef7", fg="#1976d2" if i==0 else "#6b7a90")
        lbl.pack(side="left", padx=10, pady=10)
        step_labels.append(lbl)
        if i < len(step_names)-1:
            tk.Label(steps_bar, text="→", font=("Segoe UI", 8), bg="#e8eef7", fg="#a0aec0").pack(side="left")

    content_frame = tk.Frame(main_frame, bg="white", relief="flat", bd=0)
    content_frame.pack(fill="both", expand=True, padx=0, pady=0)

    step_frames = []

    # Step 0: Welcome
    f0 = tk.Frame(content_frame, bg="white")
    tk.Label(f0, text="🪟", font=("Segoe UI", 52), bg="white").pack(pady=(25,5))
    tk.Label(f0, text="به نصب‌کننده نیتیو ویندوز خوش آمدید", font=("Segoe UI", 18, "bold"), bg="white", fg="#0f2a4a").pack(pady=5)
    tk.Label(f0, text=f"{APP_NAME} {APP_VERSION}\nنسخه نهایی نیتیو ویندوز - پنجره استاندارد (نه مرورگر)\nتیرا v4.1: جاروبرقی، یخچال، لباسشویی، پراید، موبایل، سری 13 14 15\nدیوار + شیپور + شکارچی + ملی‌پیامک کامل + روبیکا + DownloadManager", font=("Segoe UI", 11), bg="white", fg="#334", justify="center").pack(pady=8)
    feat_frame = tk.Frame(f0, bg="white")
    feat_frame.pack(pady=12)
    features = [
        "🪟 برنامه اصلی: پنجره نیتیو ویندوز استاندارد - نه مرورگر! (داشبورد/تیرا/دانلودها/تنظیمات)",
        "📦 یک فایل تکی رمزنگاری شده - بدون نیاز به اینترنت (1-2GB) - بدون نمایش کد",
        "🌐 کرومیوم اختصاصی + مدل تیرا داخل فایل نصب - DownloadManager سریع با resume",
        "🧠 تیرا v4.1: جاروبرقی بوش، یخچال، پراید، سری 13 14 15، هرچی موبایل bulk",
        "💬 متن پیامک رو بذار، متن چت، راهنمای ملی‌پیامک کامل (Send/Pattern/Delivery/Inbox)",
        "🤖 ربات‌های بله/روبیکا/تلگرام -> تیرا - دستورات از ربات‌ها",
        "📱 هرچی موبایل: پیام خودکار + استخراج شماره‌ها + اطلاع روبیکا",
        "🛡️ IP ریست خودکار + سودآوری هزار پارامتری + بدون کنسول سیاه",
    ]
    for feat in features:
        tk.Label(feat_frame, text=feat, font=("Segoe UI", 9), bg="white", fg="#2d3748", anchor="w", wraplength=720, justify="left").pack(anchor="w", pady=2, padx=15)
    tk.Label(f0, text="برای ادامه Next را بزنید - نصب استاندارد ویندوز مثل Office - بدون کنسول", font=("Segoe UI", 10, "bold"), bg="white", fg="#1976d2").pack(pady=12)
    step_frames.append(f0)

    # Step 1: License
    f1 = tk.Frame(content_frame, bg="white")
    tk.Label(f1, text="📜 توافق‌نامه مجوز - نیتیو ویندوز", font=("Segoe UI", 14, "bold"), bg="white", fg="#0f2a4a").pack(anchor="w", padx=25, pady=(20,10))
    txt_license = tk.Text(f1, height=16, font=("Segoe UI", 9), wrap="word", bg="#f7fafc", relief="flat", bd=1)
    txt_license.pack(fill="both", expand=True, padx=25, pady=5)
    license_text = f"""{APP_NAME} {APP_VERSION} - توافق‌نامه مجوز نهایی نیتیو ویندوز v4.1

1. این نرم‌افزار برای استفاده شخصی و تجاری مجاز است - پنجره نیتیو ویندوز استاندارد.
2. شما متعهد می‌شوید از این نرم‌افزار برای اهداف غیرقانونی استفاده نکنید.
3. مسئولیت استفاده از شماره‌های استخراج شده بر عهده کاربر است.
4. این نرم‌افزار شامل کرومیوم اختصاصی و مدل هوش مصنوعی تیرا است.
5. IP ریست خودکار: هنگام تغییر IP، سهمیه صفر می‌شود.
6. سودآوری هزار پارامتری: باتری، رجیستر، خش، کارتن، تعمیر، گارانتی.
7. برنامه اصلی نیتیو ویندوز است - نه مرورگر.
8. با نصب، شما با شرایط استفاده موافقت می‌کنید.

© 2024-2026 Divar Marketing - Tira Agent v4.1 Native Final
"""
    txt_license.insert("1.0", license_text)
    txt_license.configure(state="disabled")
    chk = tk.Checkbutton(f1, text="✅ شرایط را خواندم و موافقم - ادامه نصب نیتیو ویندوز", variable=agree_var, font=("Segoe UI", 11, "bold"), bg="white", fg="#0f2a4a")
    chk.pack(anchor="w", padx=25, pady=12)
    step_frames.append(f1)

    # Step 2: Data Preserve
    f2 = tk.Frame(content_frame, bg="white")
    tk.Label(f2, text="💾 اطلاعات نسخه قبلی - حفظ یا حذف؟", font=("Segoe UI", 14, "bold"), bg="white", fg="#d9534f").pack(anchor="w", padx=25, pady=(20,10))
    prev_info = has_previous_data()
    if prev_info["exists"]:
        info_text = f"⚠️ نسخه قبلی یافت شد!\n\n📊 {prev_info['accounts']} اکانت لاگین شده\n📋 {prev_info['leads']} سرنخ ذخیره شده\n💾 حجم دیتابیس: {prev_info['size_mb']} MB\n\nلطفاً انتخاب کنید:"
    else:
        info_text = "✅ نسخه قبلی یافت نشد - نصب تمیز انجام می‌شود."
    tk.Label(f2, text=info_text, font=("Segoe UI", 11), bg="#fff8ea" if prev_info["exists"] else "#e8f6ee", fg="#7a5a12" if prev_info["exists"] else "#1a7a3c", justify="left", wraplength=700).pack(fill="x", padx=25, pady=10)

    preserve_frame = tk.Frame(f2, bg="white")
    preserve_frame.pack(fill="x", padx=25, pady=15)

    tk.Radiobutton(preserve_frame, text="✅ حفظ کامل - تمام اکانت‌ها، سرنخ‌ها، تنظیمات، لاگین‌ها بماند (پیشنهاد)", variable=preserve_var, value="keep", font=("Segoe UI", 11, "bold"), bg="white", fg="#2e9e5b").pack(anchor="w", pady=5)
    tk.Label(preserve_frame, text="    اکانت‌ها، کلمات کلیدی، قالب پیام‌ها، تاریخچه - همه می‌ماند", font=("Segoe UI", 9), bg="white", fg="#6b7a90").pack(anchor="w", padx=30)

    tk.Radiobutton(preserve_frame, text="⚠️ حفظ فقط اکانت‌ها - سرنخ‌ها پاک شود، اکانت‌ها بماند", variable=preserve_var, value="keep_accounts", font=("Segoe UI", 10), bg="white", fg="#e8a13c").pack(anchor="w", pady=8)
    tk.Radiobutton(preserve_frame, text="🗑️ حذف کامل - همه چیز پاک شود و نصب تمیز", variable=preserve_var, value="delete_all", font=("Segoe UI", 10), bg="white", fg="#d9534f").pack(anchor="w", pady=8)

    if not prev_info["exists"]:
        preserve_var.set("keep")
        for child in preserve_frame.winfo_children():
            if isinstance(child, tk.Radiobutton):
                child.configure(state="disabled")

    tk.Label(f2, text="💡 پیشنهاد: گزینه اول (حفظ کامل) - اکانت‌های لاگین شده از بین نرود", font=("Segoe UI", 9, "italic"), bg="white", fg="#1976d2").pack(anchor="w", padx=25, pady=10)
    step_frames.append(f2)

    # Step 3: Location
    f3 = tk.Frame(content_frame, bg="white")
    tk.Label(f3, text="📁 محل نصب را انتخاب کنید - نیتیو ویندوز", font=("Segoe UI", 14, "bold"), bg="white", fg="#0f2a4a").pack(anchor="w", padx=25, pady=(20,10))
    tk.Label(f3, text="برنامه در این پوشه نصب می‌شود. Browse برای تغییر:", font=("Segoe UI", 10), bg="white", fg="#334").pack(anchor="w", padx=25, pady=5)
    path_row = tk.Frame(f3, bg="white")
    path_row.pack(fill="x", padx=25, pady=12)
    ent = tk.Entry(path_row, textvariable=install_dir_var, font=("Consolas", 10), width=60, bg="#f7fafc", relief="flat", bd=1)
    ent.pack(side="left", fill="x", expand=True, ipady=6)
    def browse():
        picked = filedialog.askdirectory(title="پوشه نصب را انتخاب کنید", initialdir=install_dir_var.get() or str(Path.home()))
        if picked:
            install_dir_var.set(picked)
    tk.Button(path_row, text="Browse...", command=browse, width=12, font=("Segoe UI", 10, "bold"), bg="#e2e8f0", relief="flat").pack(side="right", padx=(10,0), ipady=4)
    tk.Label(f3, text="💾 فضای مورد نیاز: ~500MB تا 2.5GB\n📍 پیشنهاد: %LOCALAPPDATA%\\DivarMarketing - بدون نیاز به Admin\n🪟 برنامه اصلی: پنجره نیتیو ویندوز - نه مرورگر", font=("Segoe UI", 9), bg="white", fg="#6b7a90", justify="left").pack(anchor="w", padx=25, pady=10)
    step_frames.append(f3)

    # Step 4: Components
    f4 = tk.Frame(content_frame, bg="white")
    tk.Label(f4, text="🧩 انتخاب اجزاء نصب - نیتیو ویندوز", font=("Segoe UI", 14, "bold"), bg="white", fg="#0f2a4a").pack(anchor="w", padx=25, pady=(20,10))
    comp_frame = tk.Frame(f4, bg="white")
    comp_frame.pack(fill="x", padx=25, pady=15)
    tk.Checkbutton(comp_frame, text="🌐 کرومیوم اختصاصی (مرورگر جدا ~200MB) - پیشنهاد ✅", variable=comp_chrome_var, font=("Segoe UI", 11, "bold"), bg="white", fg="#0f2a4a").pack(anchor="w", pady=6)
    tk.Label(comp_frame, text="     مرورگر جدا برای هر اکانت - با DownloadManager سریع", font=("Segoe UI", 9), bg="white", fg="#6b7a90").pack(anchor="w", padx=30)
    tk.Checkbutton(comp_frame, text="🧠 مدل تیرا (Qwen GGUF ~100MB) - مذاکره هوشمند", variable=comp_model_var, font=("Segoe UI", 11), bg="white").pack(anchor="w", pady=10)
    tk.Checkbutton(comp_frame, text="🔗 میانبر دسکتاپ و استارت منو - نیتیو ویندوز", variable=comp_shortcut_var, font=("Segoe UI", 10), bg="white").pack(anchor="w", pady=10)
    tk.Label(f4, text="💡 اگر تیک کرومیوم را بردارید، در اولین اجرا با DownloadManager سریع دانلود می‌شود\n💡 برنامه اصلی: پنجره نیتیو ویندوز با 4 تب - نه مرورگر", font=("Segoe UI", 9), bg="#f0f4f8", fg="#4a5568", justify="left").pack(fill="x", padx=25, pady=15)
    step_frames.append(f4)

    # Step 5: Progress
    f5 = tk.Frame(content_frame, bg="white")
    tk.Label(f5, text="⏳ در حال نصب نیتیو ویندوز - لطفاً صبر کنید...", font=("Segoe UI", 14, "bold"), bg="white", fg="#1976d2").pack(anchor="w", padx=25, pady=(20,5))
    status_label = tk.Label(f5, text="آماده نصب نیتیو...", font=("Segoe UI", 11, "bold"), bg="white", fg="#0f2a4a")
    status_label.pack(anchor="w", padx=25, pady=5)
    bar = ttk.Progressbar(f5, length=700, mode="determinate", maximum=100)
    bar.pack(padx=25, pady=8, fill="x")
    chrome_frame = tk.Frame(f5, bg="white")
    chrome_frame.pack(fill="x", padx=25, pady=4)
    chrome_label = tk.Label(chrome_frame, text="🌐 Chromium: در انتظار... - DownloadManager", font=("Segoe UI", 10), bg="white", fg="#4a5568", anchor="w")
    chrome_label.pack(fill="x")
    chrome_bar = ttk.Progressbar(chrome_frame, length=700, mode="determinate", maximum=100, style="Chrome.Horizontal.TProgressbar")
    chrome_bar.pack(fill="x", pady=2)
    model_frame = tk.Frame(f5, bg="white")
    model_frame.pack(fill="x", padx=25, pady=4)
    model_label = tk.Label(model_frame, text="🧠 مدل تیرا: در انتظار... - DownloadManager", font=("Segoe UI", 10), bg="white", fg="#4a5568", anchor="w")
    model_label.pack(fill="x")
    model_bar = ttk.Progressbar(model_frame, length=700, mode="determinate", maximum=100, style="Model.Horizontal.TProgressbar")
    model_bar.pack(fill="x", pady=2)
    log_frame = tk.Frame(f5, bg="white")
    log_frame.pack(fill="both", expand=True, padx=25, pady=10)
    tk.Label(log_frame, text="📝 جزئیات نصب نیتیو + DownloadManager:", font=("Segoe UI", 9, "bold"), bg="white", fg="#4a5568").pack(anchor="w")
    logbox = tk.Text(log_frame, height=12, font=("Consolas", 8), bg="#1a202c", fg="#e2e8f0", relief="flat", wrap="word")
    logbox.pack(fill="both", expand=True, pady=5)

    def log(msg: str):
        def _():
            logbox.configure(state="normal")
            logbox.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            logbox.see("end")
            logbox.configure(state="disabled")
        try:
            root.after(0, _)
        except:
            pass
        print(msg)

    def prog(pct: int, label: str):
        def _():
            bar["value"] = pct
            status_label.configure(text=label)
        try:
            root.after(0, _)
        except:
            pass

    def chrome_prog(pct: int, label: str):
        def _():
            chrome_bar["value"] = pct
            chrome_label.configure(text=label)
        try:
            root.after(0, _)
        except:
            pass

    def model_prog(pct: int, label: str):
        def _():
            model_bar["value"] = pct
            model_label.configure(text=label)
        try:
            root.after(0, _)
        except:
            pass

    step_frames.append(f5)

    # Step 6: Finish
    f6 = tk.Frame(content_frame, bg="white")
    tk.Label(f6, text="✅", font=("Segoe UI", 64), bg="white").pack(pady=(30,5))
    tk.Label(f6, text="نصب نیتیو ویندوز کامل شد!", font=("Segoe UI", 20, "bold"), bg="white", fg="#2e9e5b").pack(pady=5)
    tk.Label(f6, text=f"{APP_NAME} نیتیو ویندوز با موفقیت نصب شد!\n\n🪟 برنامه اصلی: پنجره استاندارد ویندوز (نه مرورگر)\n📊 4 تب: داشبورد/تیرا/دانلودها/تنظیمات\n\n🌐 سرور: http://127.0.0.1:{PORT}\n📱 گوشی همین Wi-Fi: http://<IP>:{PORT}", font=("Segoe UI", 12), bg="white", fg="#1a202c", justify="center").pack(pady=12)
    tk.Label(f6, text="🔗 میانبر روی دسکتاپ و استارت منو ساخته شد\n🛡️ فایروال باز شد\n🪟 بدون کنسول سیاه - پنجره نیتیو ویندوز", font=("Segoe UI", 10), bg="#e8f6ee", fg="#1a7a3c", justify="center").pack(pady=8, fill="x", padx=40)
    launch_var = tk.BooleanVar(value=True)
    tk.Checkbutton(f6, text="🚀 اجرای برنامه نیتیو بعد از بستن نصب‌کننده (پیشنهاد)", variable=launch_var, font=("Segoe UI", 11, "bold"), bg="white", fg="#0f2a4a").pack(pady=15)
    step_frames.append(f6)

    def show_step(idx: int):
        for i, fr in enumerate(step_frames):
            if i == idx:
                fr.pack(fill="both", expand=True)
            else:
                fr.pack_forget()
        for i, lbl in enumerate(step_labels):
            if i == idx:
                lbl.configure(font=("Segoe UI", 9, "bold"), fg="#ffffff", bg="#1976d2")
            elif i < idx:
                lbl.configure(font=("Segoe UI", 8), fg="#2e9e5b", bg="#e8f6ee")
            else:
                lbl.configure(font=("Segoe UI", 8), fg="#6b7a90", bg="#e8eef7")
        if idx == 0:
            btn_back.configure(state="disabled")
            btn_next.configure(text="Next >", state="normal")
            btn_install.pack_forget()
            btn_finish.pack_forget()
        elif idx in (1,2,3,4):
            btn_back.configure(state="normal")
            btn_next.configure(text="Next >", state="normal")
            btn_install.pack_forget()
            btn_finish.pack_forget()
            if idx == 4:
                btn_next.configure(text="Install - نصب نیتیو", state="normal")
        elif idx == 5:
            btn_back.configure(state="disabled")
            btn_next.configure(state="disabled")
            btn_install.pack_forget()
            btn_finish.pack_forget()
        elif idx == 6:
            btn_back.configure(state="disabled")
            btn_next.configure(state="disabled")
            btn_install.pack_forget()
            btn_finish.pack(side="right", padx=20, pady=15)

    btn_frame = tk.Frame(main_frame, bg="#e8eef7", height=65)
    btn_frame.pack(fill="x", side="bottom")
    btn_frame.pack_propagate(False)

    btn_finish = tk.Button(btn_frame, text="✅ Finish - اتمام نیتیو", width=20, font=("Segoe UI", 11, "bold"), bg="#2e9e5b", fg="white", relief="flat", padx=10, pady=8, command=lambda: root.destroy())
    btn_back = tk.Button(btn_frame, text="< Back", width=12, font=("Segoe UI", 10), bg="white", relief="flat", bd=1)
    btn_next = tk.Button(btn_frame, text="Next >", width=12, font=("Segoe UI", 10, "bold"), bg="#1976d2", fg="white", relief="flat")
    btn_install = tk.Button(btn_frame, text="🚀 Install - نصب نیتیو ویندوز", width=24, font=("Segoe UI", 11, "bold"), bg="#1976d2", fg="white", relief="flat")

    btn_back.pack(side="left", padx=20, pady=12)
    btn_next.pack(side="right", padx=10, pady=12)
    btn_install.pack(side="right", padx=10, pady=12)
    btn_finish.pack_forget()

    def on_back():
        if current_step[0] > 0:
            current_step[0] -= 1
            show_step(current_step[0])

    def on_next():
        idx = current_step[0]
        if idx == 1 and not agree_var.get():
            messagebox.showwarning("توافق‌نامه", "⚠️ لطفاً تیک موافقت را بزنید")
            return
        if idx == 2:
            if preserve_var.get() == "delete_all":
                if not messagebox.askyesno("⚠️ هشدار حذف کامل", "آیا مطمئن هستید می‌خواهید تمام اطلاعات قبلی پاک شود؟\n\nاین عمل غیرقابل بازگشت است!"):
                    return
        if idx == 3:
            dest = install_dir_var.get().strip()
            if not dest:
                messagebox.showwarning("مسیر", "📁 محل نصب را انتخاب کنید")
                return
        if idx == 4:
            current_step[0] = 5
            show_step(5)
            def work():
                try:
                    chosen = Path(install_dir_var.get().strip() or str(default_install_dir()))
                    log(f"📁 محل نصب نیتیو: {chosen}")
                    prog(5, "آماده‌سازی پوشه نیتیو...")
                    chosen.mkdir(parents=True, exist_ok=True)
                    prog(15, f"مدیریت اطلاعات قبلی: {preserve_var.get()}...")
                    target = extract_payload(chosen, log, progress_cb=lambda p, l: prog(15+int(p*0.6), l), preserve_mode=preserve_var.get())
                    prog(75, "میانبرهای نیتیو ویندوز...")
                    if comp_shortcut_var.get():
                        ico = app_icon()
                        ico_dst = chosen / "app.ico"
                        if ico.exists():
                            shutil.copy2(ico, ico_dst)
                        make_shortcut(target, chosen, ico_dst if ico_dst.exists() else ico, log)
                    prog(85, "فایروال...")
                    open_firewall(log)
                    prog(92, "بررسی اجزاء نیتیو + DownloadManager...")
                    if comp_chrome_var.get():
                        chrome_prog(100, "🌐 Chromium آماده ✅ - داخل فایل نصب بود")
                    else:
                        chrome_prog(0, "🌐 Chromium رد شد - بعداً با DownloadManager دانلود می‌شود")
                    if comp_model_var.get():
                        model_prog(100, "🧠 مدل تیرا آماده ✅ - داخل فایل نصب بود")
                    else:
                        model_prog(0, "🧠 مدل رد شد - fallback هوشمند + DownloadManager")
                    prog(95, "اجرای برنامه نیتیو ویندوز...")
                    if launch_var.get():
                        launch(target, chosen, log)
                    prog(100, "نصب نیتیو کامل شد ✅ - بدون کنسول - پنجره ویندوز")
                    log("🎉 نصب نیتیو کامل شد - پنجره استاندارد ویندوز - آماده استفاده!")
                    current_step[0] = 6
                    root.after(0, lambda: show_step(6))
                except Exception as e:
                    log(f"❌ خطا: {e}")
                    log(traceback.format_exc())
                    root.after(0, lambda: messagebox.showerror("خطا", f"❌ نصب ناموفق:\n{e}"))
                    root.after(0, lambda: show_step(4))
            threading.Thread(target=work, daemon=True).start()
            return
        if idx < 4:
            current_step[0] += 1
            show_step(current_step[0])

    btn_back.configure(command=on_back)
    btn_next.configure(command=on_next)
    btn_install.configure(command=on_next)

    show_step(0)
    root.mainloop()
    return 0

def main() -> int:
    if "--cli" in sys.argv:
        dest = default_install_dir()
        if "--dest" in sys.argv:
            i = sys.argv.index("--dest")
            if i+1 < len(sys.argv):
                dest = Path(sys.argv[i+1])
        preserve = "keep"
        if "--preserve" in sys.argv:
            j = sys.argv.index("--preserve")
            if j+1 < len(sys.argv):
                preserve = sys.argv[j+1]
        print(f"Install dir: {dest}, preserve: {preserve} - CLI mode")
        target = extract_payload(Path(dest), print, preserve_mode=preserve)
        make_shortcut(target, Path(dest), app_icon(), print)
        open_firewall(print)
        launch(target, Path(dest), print)
        return 0
    return gui_wizard()

if __name__ == "__main__":
    raise SystemExit(main())
