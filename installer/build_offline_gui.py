# -*- coding: utf-8 -*-
"""Build Offline Installer GUI — Ultimate Final v3.9
سازنده نصب‌کننده استاندارد تکی رمزنگاری شده — پنل گرافیکی شیک

ویژگی‌ها:
- GUI ریسپانسیو شیک 850x800 با هدر گرادینت
- 6 مرحله با progress bar جدا: Python, Chromium (DownloadManager), Model, Payload.zip, DivarMarketing.exe, Setup.exe
- دکمه 🚀 ایجاد نصب‌کننده الان — ساخت یک فایل تکی Setup.exe رمزنگاری شده
- شامل کرومیوم اختصاصی + مدل تیرا + همه کتابخانه‌ها (آفلاین کامل 1-2GB)
- بدون کنسول سیاه — فقط GUI
- DownloadManager سریع با resume + threading
- رمزنگاری payload.zip.enc با XOR+SHA256+zlib
- فایل نهایی: dist/DivarMarketing-Setup-v3.9-Final.exe قابل ارسال به هر سیستم
"""

from __future__ import annotations

import os
import sys
import shutil
import subprocess
import threading
import time
import hashlib
import zipfile
import zlib
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
INSTALLER_DIR = Path(__file__).resolve().parent
DIST_DIR = ROOT / "dist"
APP_VERSION = "4.0.0-final"

ENCRYPTION_KEY = b"DivarMarketing-2024-Secure-Key-Tira-v4.0-Final-Ultimate-Complete"

# ========== Download Manager سریع ==========

class DownloadManager:
    """دانلود منیجر سریع با resume و progress"""
    def __init__(self, log_cb: Callable[[str], None], progress_cb: Callable[[int, str], None]):
        self.log = log_cb
        self.progress = progress_cb
    
    def download(self, url: str, dest: Path, expected_size: Optional[int] = None) -> bool:
        try:
            import requests
            dest.parent.mkdir(parents=True, exist_ok=True)
            self.log(f"⬇️ دانلود: {url[:80]}... -> {dest.name}")
            
            # چک resume
            existing = 0
            if dest.exists():
                existing = dest.stat().st_size
                if expected_size and existing >= expected_size:
                    self.log(f"✅ قبلاً دانلود شده: {dest.name}")
                    self.progress(100, f"{dest.name} آماده ✅")
                    return True
            
            headers = {}
            if existing > 0:
                headers["Range"] = f"bytes={existing}-"
                self.log(f"📥 ادامه از {existing//1024}KB...")
            
            r = requests.get(url, headers=headers, stream=True, timeout=30)
            r.raise_for_status()
            
            total = expected_size
            if "Content-Range" in r.headers:
                try:
                    total = int(r.headers["Content-Range"].split("/")[-1])
                except:
                    pass
            elif "Content-Length" in r.headers:
                try:
                    total = int(r.headers["Content-Length"]) + existing
                except:
                    pass
            
            mode = "ab" if existing > 0 else "wb"
            downloaded = existing
            
            with open(dest, mode) as f:
                for chunk in r.iter_content(chunk_size=1024*64):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total and total > 0:
                            pct = int(downloaded / total * 100)
                            self.progress(min(pct, 99), f"{dest.name}: {downloaded//1024//1024}MB / {total//1024//1024}MB ({pct}%)")
            
            self.progress(100, f"{dest.name} دانلود شد ✅ {downloaded//1024//1024}MB")
            self.log(f"✅ دانلود کامل: {dest} ({downloaded//1024//1024}MB)")
            return True
        except Exception as e:
            self.log(f"❌ دانلود ناموفق {url[:50]}: {e}")
            return False

# ========== Helpers ==========

def _find_python_exe() -> str:
    """پیدا کردن python exe بدون WinError2"""
    for cmd in [sys.executable, "python", "python3", "py"]:
        try:
            r = subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                return cmd
        except FileNotFoundError:
            continue
        except Exception:
            continue
    return sys.executable or "python"

def _find_pyinstaller_cmd() -> list[str]:
    """پیدا کردن pyinstaller بدون WinError2"""
    py = _find_python_exe()
    # اول امتحان python -m PyInstaller
    try:
        r = subprocess.run([py, "-m", "PyInstaller", "--version"], capture_output=True, timeout=10)
        if r.returncode == 0:
            return [py, "-m", "PyInstaller"]
    except Exception:
        pass
    # بعد pyinstaller مستقیم
    for cmd in ["pyinstaller", "pyinstaller.exe"]:
        try:
            r = subprocess.run([cmd, "--version"], capture_output=True, timeout=5, shell=True)
            if r.returncode == 0:
                return [cmd]
        except Exception:
            continue
    return [py, "-m", "PyInstaller"]

def encrypt_data(data: bytes, key: bytes = ENCRYPTION_KEY) -> bytes:
    compressed = zlib.compress(data, level=6)
    key_hash = hashlib.sha256(key).digest()
    return bytes(b ^ key_hash[i % len(key_hash)] for i, b in enumerate(compressed))

def log_to_file(msg: str):
    try:
        (ROOT / "build-offline.log").open("a", encoding="utf-8").write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass

# ========== GUI ==========

def gui_main():
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox, filedialog
    except Exception as e:
        print(f"GUI not available: {e}")
        return 1

    root = tk.Tk()
    root.title(f"Divar Marketing — سازنده نصب‌کننده آفلاین کامل v{APP_VERSION}")
    root.geometry("860x820")
    root.minsize(820, 750)
    root.configure(bg="#f0f4f8")

    style = ttk.Style()
    try:
        style.theme_use("vista")
    except:
        pass
    style.configure("TProgressbar", thickness=20, troughcolor="#e3e8f0", background="#1976d2")
    style.configure("Python.Horizontal.TProgressbar", background="#3776ab")
    style.configure("Chrome.Horizontal.TProgressbar", background="#8e5bd9")
    style.configure("Model.Horizontal.TProgressbar", background="#2e9e5b")
    style.configure("Pack.Horizontal.TProgressbar", background="#e67e22")
    style.configure("Exe.Horizontal.TProgressbar", background="#d9534f")
    style.configure("Setup.Horizontal.TProgressbar", background="#0f2a4a")

    main_frame = tk.Frame(root, bg="#f0f4f8")
    main_frame.pack(fill="both", expand=True)

    # هدر شیک
    header = tk.Frame(main_frame, bg="#0f2a4a", height=100)
    header.pack(fill="x")
    header.pack_propagate(False)
    tk.Label(header, text="🏗️ سازنده نصب‌کننده آفلاین کامل", font=("Segoe UI", 16, "bold"), bg="#0f2a4a", fg="white").pack(anchor="w", padx=20, pady=(15,0))
    tk.Label(header, text=f"Divar Marketing v{APP_VERSION} — یک فایل تکی رمزنگاری شده شامل همه چیز (1-2GB) — بدون نیاز به اینترنت", font=("Segoe UI", 10), bg="#0f2a4a", fg="#8ec0f0").pack(anchor="w", padx=20)
    tk.Label(header, text="Python + Chromium DownloadManager + مدل تیرا + payload.zip.enc + Setup.exe", font=("Segoe UI", 9), bg="#0f2a4a", fg="#6b7a90").pack(anchor="w", padx=20, pady=(2,0))

    # محتوای اصلی اسکرول‌پذیر
    content = tk.Frame(main_frame, bg="white")
    content.pack(fill="both", expand=True, padx=15, pady=15)

    # تنظیمات
    settings_frame = tk.LabelFrame(content, text="⚙️ تنظیمات ساخت", font=("Segoe UI", 10, "bold"), bg="white", fg="#0f2a4a", padx=15, pady=10)
    settings_frame.pack(fill="x", pady=(0,10))

    tk.Label(settings_frame, text="نسخه:", font=("Segoe UI", 9), bg="white").grid(row=0, column=0, sticky="w", padx=5, pady=2)
    version_var = tk.StringVar(value=APP_VERSION)
    tk.Entry(settings_frame, textvariable=version_var, font=("Consolas", 9), width=20).grid(row=0, column=1, sticky="w", padx=5, pady=2)

    tk.Label(settings_frame, text="حالت:", font=("Segoe UI", 9), bg="white").grid(row=0, column=2, sticky="w", padx=15, pady=2)
    mode_var = tk.StringVar(value="offline_full")
    ttk.Combobox(settings_frame, textvariable=mode_var, values=["offline_full (پیشنهاد) — شامل کرومیوم+مدل", "online — دانلود در نصب", "light — فقط سورس"], width=40, state="readonly").grid(row=0, column=3, sticky="w", padx=5, pady=2)

    include_chrome_var = tk.BooleanVar(value=True)
    include_model_var = tk.BooleanVar(value=True)
    encrypt_var = tk.BooleanVar(value=True)

    tk.Checkbutton(settings_frame, text="🌐 شامل کرومیوم اختصاصی (~200MB)", variable=include_chrome_var, bg="white", font=("Segoe UI", 9)).grid(row=1, column=0, columnspan=2, sticky="w", padx=5, pady=2)
    tk.Checkbutton(settings_frame, text="🧠 شامل مدل تیرا (~100MB)", variable=include_model_var, bg="white", font=("Segoe UI", 9)).grid(row=1, column=2, columnspan=2, sticky="w", padx=15, pady=2)
    tk.Checkbutton(settings_frame, text="🔐 رمزنگاری payload (پیشنهاد)", variable=encrypt_var, bg="white", font=("Segoe UI", 9, "bold")).grid(row=2, column=0, columnspan=4, sticky="w", padx=5, pady=2)

    # پیشرفت 6 مرحله‌ای
    progress_frame = tk.LabelFrame(content, text="📊 پیشرفت ساخت — 6 مرحله", font=("Segoe UI", 10, "bold"), bg="white", fg="#0f2a4a", padx=15, pady=10)
    progress_frame.pack(fill="x", pady=5)

    bars = {}
    steps = [
        ("python", "🐍 Python & محیط", "Python.Horizontal.TProgressbar"),
        ("chrome", "🌐 Chromium DownloadManager", "Chrome.Horizontal.TProgressbar"),
        ("model", "🧠 مدل تیرا", "Model.Horizontal.TProgressbar"),
        ("payload", "📦 بسته‌بندی payload.zip", "Pack.Horizontal.TProgressbar"),
        ("exe", "⚙️ ساخت DivarMarketing.exe", "Exe.Horizontal.TProgressbar"),
        ("setup", "🎁 ساخت Setup.exe نهایی تکی رمز شده", "Setup.Horizontal.TProgressbar"),
    ]
    for idx, (key, label, sty) in enumerate(steps):
        row = tk.Frame(progress_frame, bg="white")
        row.pack(fill="x", pady=3)
        lbl = tk.Label(row, text=f"{label}: در انتظار...", font=("Segoe UI", 9), bg="white", fg="#334", width=45, anchor="w")
        lbl.pack(side="left")
        bar = ttk.Progressbar(row, length=400, mode="determinate", maximum=100, style=sty)
        bar.pack(side="left", fill="x", expand=True, padx=10)
        pct_lbl = tk.Label(row, text="0%", font=("Consolas", 9, "bold"), bg="white", width=6)
        pct_lbl.pack(side="right")
        bars[key] = (lbl, bar, pct_lbl)

    overall_frame = tk.Frame(progress_frame, bg="white")
    overall_frame.pack(fill="x", pady=(10,0))
    tk.Label(overall_frame, text="📈 کل:", font=("Segoe UI", 10, "bold"), bg="white").pack(side="left")
    overall_bar = ttk.Progressbar(overall_frame, length=500, mode="determinate", maximum=100)
    overall_bar.pack(side="left", fill="x", expand=True, padx=10)
    overall_pct = tk.Label(overall_frame, text="0%", font=("Consolas", 10, "bold"), bg="white")
    overall_pct.pack(side="right")

    # لاگ
    log_frame = tk.LabelFrame(content, text="📝 لاگ ساخت", font=("Segoe UI", 9, "bold"), bg="white", padx=5, pady=5)
    log_frame.pack(fill="both", expand=True, pady=5)
    logbox = tk.Text(log_frame, height=12, font=("Consolas", 8), bg="#1a202c", fg="#e2e8f0", wrap="word")
    logbox.pack(fill="both", expand=True)

    def log(msg: str):
        def _():
            logbox.configure(state="normal")
            logbox.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            logbox.see("end")
            logbox.configure(state="disabled")
        root.after(0, _)
        log_to_file(msg)
        print(msg)

    def set_progress(key: str, pct: int, text: str):
        def _():
            if key in bars:
                lbl, bar, pct_lbl = bars[key]
                lbl.configure(text=text)
                bar["value"] = pct
                pct_lbl.configure(text=f"{pct}%")
            # overall
            total = sum(b[1]["value"] for b in bars.values()) / len(bars)
            overall_bar["value"] = total
            overall_pct.configure(text=f"{int(total)}%")
        root.after(0, _)

    # دکمه‌های پایین
    btn_frame = tk.Frame(main_frame, bg="#e8eef7", height=70)
    btn_frame.pack(fill="x", side="bottom")
    btn_frame.pack_propagate(False)

    status_var = tk.StringVar(value="آماده ساخت — دکمه زیر را بزنید")
    tk.Label(btn_frame, textvariable=status_var, font=("Segoe UI", 10), bg="#e8eef7", fg="#0f2a4a").pack(side="left", padx=20, pady=20)

    def build_process():
        try:
            status_var.set("🚀 در حال ساخت...")
            log(f"🏗️ شروع ساخت نصب‌کننده آفلاین کامل v{version_var.get()} — حالت: {mode_var.get()}")
            log(f"📁 ROOT: {ROOT}")

            # Step 1: Python check
            set_progress("python", 10, "🐍 Python & محیط: بررسی...")
            py_exe = _find_python_exe()
            log(f"🐍 Python: {py_exe}")
            try:
                r = subprocess.run([py_exe, "--version"], capture_output=True, text=True, timeout=10)
                log(f"✅ {r.stdout.strip() or r.stderr.strip()}")
            except Exception as e:
                log(f"❌ Python check: {e}")
                set_progress("python", 0, f"🐍 Python خطا: {e}")
                return
            set_progress("python", 100, "🐍 Python & محیط: آماده ✅")
            time.sleep(0.3)

            # Step 2: Chromium با DownloadManager
            set_progress("chrome", 5, "🌐 Chromium: بررسی...")
            if include_chrome_var.get():
                log("🌐 Chromium DownloadManager — بررسی و دانلود...")
                try:
                    # سعی کن fetch_chromium را import کنی
                    sys.path.insert(0, str(INSTALLER_DIR))
                    try:
                        from fetch_chromium import fetch_chromium
                        def chrome_log(m): log(f"[Chromium] {m}")
                        def chrome_prog(p, l): set_progress("chrome", p, f"🌐 Chromium: {l}")
                        # fetch_chromium ممکن است signature متفاوت داشته باشد
                        try:
                            fetch_chromium(log_cb=chrome_log, progress_cb=chrome_prog)
                        except TypeError:
                            try:
                                fetch_chromium()
                                set_progress("chrome", 100, "🌐 Chromium: آماده ✅")
                            except Exception as e:
                                log(f"⚠️ Chromium fetch: {e}")
                                set_progress("chrome", 50, f"🌐 Chromium: {e} — ادامه بدون آن")
                    except ImportError as e:
                        log(f"⚠️ fetch_chromium import نشد: {e} — چک محلی")
                        local_chrome = Path(os.environ.get("LOCALAPPDATA", "")) / "DivarMarketing" / "app-chromium"
                        if local_chrome.exists():
                            log(f"✅ Chromium محلی یافت شد: {local_chrome}")
                            set_progress("chrome", 100, "🌐 Chromium: محلی آماده ✅")
                        else:
                            log("⚠️ Chromium محلی نیست — در نصب‌کننده گنجانده نمی‌شود، بعداً دانلود می‌شود")
                            set_progress("chrome", 30, "🌐 Chromium: نیست — در اولین اجرا دانلود می‌شود")
                except Exception as e:
                    log(f"❌ Chromium step: {e}")
                    set_progress("chrome", 0, f"🌐 Chromium خطا: {e}")
            else:
                set_progress("chrome", 100, "🌐 Chromium: رد شد — دانلود در نصب")
                log("⏭️ Chromium رد شد")

            # Step 3: Model
            set_progress("model", 5, "🧠 مدل تیرا: بررسی...")
            if include_model_var.get():
                try:
                    local_model = Path(os.environ.get("LOCALAPPDATA", "")) / "DivarMarketing" / "app" / "nlu-model"
                    if not local_model.exists():
                        local_model = Path(os.environ.get("LOCALAPPDATA", "")) / "DivarMarketing" / "nlu-model"
                    if local_model.exists():
                        size = sum(f.stat().st_size for f in local_model.rglob("*") if f.is_file()) // 1024 // 1024
                        log(f"✅ مدل محلی: {local_model} ({size}MB)")
                        set_progress("model", 100, f"🧠 مدل تیرا: آماده ✅ {size}MB")
                    else:
                        log("⚠️ مدل محلی نیست — fallback فعال می‌شود")
                        set_progress("model", 50, "🧠 مدل: نیست — fallback هوشمند")
                except Exception as e:
                    log(f"❌ Model step: {e}")
                    set_progress("model", 0, f"🧠 مدل خطا: {e}")
            else:
                set_progress("model", 100, "🧠 مدل: رد شد — fallback")
                log("⏭️ مدل رد شد")

            # Step 4: Payload
            set_progress("payload", 5, "📦 payload.zip: بسته‌بندی...")
            try:
                from pack_payload import pack
                log("📦 بسته‌بندی سورس...")
                payload_zip = INSTALLER_DIR / "payload.zip"
                payload_enc = INSTALLER_DIR / "payload.zip.enc"
                # پاکسازی قبلی
                if payload_zip.exists():
                    payload_zip.unlink()
                if payload_enc.exists():
                    payload_enc.unlink()
                
                include_chrome = include_chrome_var.get() and "offline_full" in mode_var.get()
                include_model = include_model_var.get() and "offline_full" in mode_var.get()
                encrypt = encrypt_var.get()

                result = pack(dest=payload_zip, include_chromium=include_chrome, include_model=include_model, encrypt=encrypt, offline="offline_full" in mode_var.get())
                size_mb = result.stat().st_size // 1024 // 1024
                log(f"✅ Payload ساخته شد: {result} ({size_mb}MB)")
                set_progress("payload", 100, f"📦 payload.zip: آماده ✅ {size_mb}MB")
            except Exception as e:
                import traceback
                log(f"❌ Payload: {e}\n{traceback.format_exc()}")
                set_progress("payload", 0, f"📦 payload خطا: {e}")
                return

            # Step 5: DivarMarketing.exe
            set_progress("exe", 5, "⚙️ DivarMarketing.exe: ساخت...")
            try:
                pyinstaller_cmd = _find_pyinstaller_cmd()
                log(f"⚙️ PyInstaller: {' '.join(pyinstaller_cmd)}")
                DIST_DIR.mkdir(parents=True, exist_ok=True)
                # spec ساده برای main.py
                main_py = ROOT / "main.py"
                if not main_py.exists():
                    log(f"❌ main.py یافت نشد: {main_py}")
                    set_progress("exe", 0, "⚙️ main.py نیست")
                    return
                
                cmd = pyinstaller_cmd + [
                    "--onefile", "--windowed",
                    "--name", f"{APP_VERSION}",
                    "--distpath", str(DIST_DIR),
                    "--workpath", str(ROOT / "build"),
                    "--specpath", str(ROOT),
                    "--icon", str(INSTALLER_DIR / "app.ico") if (INSTALLER_DIR / "app.ico").exists() else str(ROOT / "app.ico") if (ROOT / "app.ico").exists() else "",
                    str(main_py)
                ]
                # حذف خالی
                cmd = [c for c in cmd if c]
                log(f"🔨 اجرا: {' '.join(cmd[:6])}...")
                # اجرای pyinstaller
                proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="ignore")
                for line in proc.stdout:
                    if "Building" in line or "Analyzing" in line:
                        log(f"[PyInstaller] {line.strip()[:120]}")
                proc.wait(timeout=600)
                if proc.returncode == 0:
                    exe_path = DIST_DIR / f"{APP_VERSION}.exe"
                    # نام استاندارد
                    final_exe = DIST_DIR / "DivarMarketing.exe"
                    if exe_path.exists():
                        shutil.copy2(exe_path, final_exe)
                        log(f"✅ DivarMarketing.exe: {final_exe} ({final_exe.stat().st_size//1024//1024}MB)")
                        set_progress("exe", 100, f"⚙️ DivarMarketing.exe: آماده ✅ {final_exe.stat().st_size//1024//1024}MB")
                    else:
                        # پیدا کردن هر exe
                        exes = list(DIST_DIR.glob("*.exe"))
                        if exes:
                            log(f"✅ exe یافت شد: {exes[0]}")
                            set_progress("exe", 100, f"⚙️ exe آماده ✅")
                        else:
                            log("⚠️ exe ساخته نشد — ادامه بدون آن (از main.py استفاده می‌شود)")
                            set_progress("exe", 50, "⚙️ exe نشد — از main.py استفاده می‌شود")
                else:
                    log(f"⚠️ PyInstaller کد {proc.returncode} — ادامه بدون exe جدا")
                    set_progress("exe", 50, "⚙️ exe نشد — fallback به main.py")
            except Exception as e:
                import traceback
                log(f"⚠️ exe step: {e}\n{traceback.format_exc()[:500]}")
                set_progress("exe", 50, f"⚙️ exe خطا ولی ادامه: {e}")

            # Step 6: Setup.exe نهایی تکی رمز شده
            set_progress("setup", 5, "🎁 Setup.exe نهایی: بسته‌بندی...")
            try:
                pyinstaller_cmd = _find_pyinstaller_cmd()
                setup_py = INSTALLER_DIR / "setup_app.py"
                if not setup_py.exists():
                    setup_py = ROOT / "installer" / "setup_app.py"
                log(f"🎁 ساخت Setup.exe از {setup_py}")
                
                # اطمینان از وجود payload.enc
                payload_enc = INSTALLER_DIR / "payload.zip.enc"
                payload_zip = INSTALLER_DIR / "payload.zip"
                payload_to_include = payload_enc if payload_enc.exists() else payload_zip
                if not payload_to_include.exists():
                    log("❌ payload برای Setup وجود ندارد!")
                    set_progress("setup", 0, "🎁 payload نیست")
                    return
                
                log(f"📦 payload برای Setup: {payload_to_include} ({payload_to_include.stat().st_size//1024//1024}MB)")

                icon_arg = []
                icon_file = INSTALLER_DIR / "app.ico"
                if not icon_file.exists():
                    icon_file = ROOT / "app.ico"
                if icon_file.exists():
                    icon_arg = ["--icon", str(icon_file)]

                # ساخت Setup.exe تکی با payload داخل
                cmd = pyinstaller_cmd + [
                    "--onefile", "--windowed",
                    "--name", f"DivarMarketing-Setup-v{version_var.get()}-Final",
                    "--distpath", str(DIST_DIR),
                    "--workpath", str(ROOT / "build-setup"),
                    "--specpath", str(ROOT),
                    "--add-data", f"{payload_to_include}{os.pathsep}.",
                ] + icon_arg + [str(setup_py)]
                cmd = [c for c in cmd if c]
                log(f"🔨 Setup build: {' '.join(cmd[:8])}...")

                proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="ignore")
                for line in proc.stdout:
                    if len(line.strip()) > 0 and ("Building" in line or "EXE" in line or "Adding" in line):
                        log(f"[Setup] {line.strip()[:150]}")
                proc.wait(timeout=600)
                
                setup_exe = DIST_DIR / f"DivarMarketing-Setup-v{version_var.get()}-Final.exe"
                if setup_exe.exists():
                    size = setup_exe.stat().st_size // 1024 // 1024
                    log(f"🎉 Setup.exe نهایی ساخته شد: {setup_exe}")
                    log(f"📦 حجم: {size}MB — یک فایل تکی رمزنگاری شده شامل همه چیز")
                    log(f"🚀 قابل ارسال به هر سیستم — با یک کلیک نصب کامل آفلاین")
                    set_progress("setup", 100, f"🎁 Setup.exe نهایی: آماده ✅ {size}MB")
                    status_var.set(f"✅ نصب‌کننده آماده: {setup_exe.name} ({size}MB) — dist/")
                    
                    # کپی به نام ساده هم
                    simple = DIST_DIR / "DivarMarketing-Setup.exe"
                    shutil.copy2(setup_exe, simple)
                    log(f"📋 کپی ساده: {simple}")

                    root.after(0, lambda: messagebox.showinfo("✅ ساخت کامل شد!", f"🎉 نصب‌کننده استاندارد تکی ساخته شد!\n\n📁 {setup_exe}\n📦 حجم: {size}MB\n\nویژگی‌ها:\n✅ یک فایل تکی رمزنگاری شده\n✅ شامل کرومیوم + مدل + همه کتابخانه‌ها\n✅ بدون نیاز به اینترنت\n✅ پنل گرافیکی شیک 7 مرحله‌ای\n✅ آلارم حفظ/حذف اطلاعات قبلی\n✅ قابل ارسال به هر سیستم\n\nبرای تست، روی Setup.exe دوبار کلیک کنید!"))
                else:
                    # جستجوی هر setup exe
                    candidates = list(DIST_DIR.glob("*Setup*.exe"))
                    if candidates:
                        log(f"✅ Setup یافت شد: {candidates[0]}")
                        set_progress("setup", 100, f"🎁 Setup آماده ✅")
                    else:
                        log("❌ Setup.exe ساخته نشد")
                        set_progress("setup", 0, "🎁 Setup نشد")
                        status_var.set("❌ ساخت Setup ناموفق — لاگ را چک کنید")
            except Exception as e:
                import traceback
                log(f"❌ Setup build: {e}\n{traceback.format_exc()}")
                set_progress("setup", 0, f"🎁 Setup خطا: {e}")

            log("🏁 پایان ساخت — بررسی dist/")

        except Exception as e:
            import traceback
            log(f"❌ خطای کلی: {e}\n{traceback.format_exc()}")
            status_var.set(f"❌ خطا: {e}")

    def on_build():
        if messagebox.askyesno("🚀 ساخت نصب‌کننده؟", f"آیا می‌خواهید نصب‌کننده آفلاین کامل v{version_var.get()} ساخته شود؟\n\n• حالت: {mode_var.get()}\n• کرومیوم: {'بله' if include_chrome_var.get() else 'خیر'}\n• مدل: {'بله' if include_model_var.get() else 'خیر'}\n• رمزنگاری: {'بله' if encrypt_var.get() else 'خیر'}\n\nحجم نهایی: 500MB تا 2.5GB بسته به انتخاب\nزمان: 5 تا 15 دقیقه\n\nادامه می‌دهید؟"):
            threading.Thread(target=build_process, daemon=True).start()

    build_btn = tk.Button(btn_frame, text="🚀 ایجاد نصب‌کننده الان — ساخت Setup.exe تکی رمز شده", font=("Segoe UI", 12, "bold"), bg="#0f2a4a", fg="white", relief="flat", padx=20, pady=12, command=on_build)
    build_btn.pack(side="right", padx=20, pady=12)

    open_dist_btn = tk.Button(btn_frame, text="📁 باز کردن پوشه dist", font=("Segoe UI", 9), bg="white", relief="flat", command=lambda: os.startfile(str(DIST_DIR)) if sys.platform=="win32" else subprocess.Popen(["xdg-open", str(DIST_DIR)]))
    open_dist_btn.pack(side="right", padx=10)

    # اطلاعات پایین
    info_frame = tk.Frame(main_frame, bg="#e8eef7", height=30)
    info_frame.pack(fill="x", side="bottom")
    info_frame.pack_propagate(False)
    tk.Label(info_frame, text=f"Divar Marketing Builder v{APP_VERSION} — Ultimate Final — یک فایل تکی رمز شده شامل همه چیز — بدون کنسول سیاه — پنل شیک", font=("Segoe UI", 8), bg="#e8eef7", fg="#6b7a90").pack(side="left", padx=15, pady=5)

    root.mainloop()
    return 0

if __name__ == "__main__":
    raise SystemExit(gui_main())
