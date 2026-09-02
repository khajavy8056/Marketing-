# -*- coding: utf-8 -*-
"""Build Offline Installer GUI — v4.2 Fixed No Freeze — Root Cause Fixed

مشکل قبلی: در مرحله بسته‌بندی گیر می‌کرد و قفل می‌کرد، هیچ لاگی نداشت
علت‌ها:
- pack_payload.py: WinError 2/5/32/123/206 بدون هندل + هیچ progress
- Double compression: zip level 6 + zlib level 6 روی 1-2GB → RAM 4GB + freeze
- کل payload.zip یکجا read_bytes → MemoryError
- فایل‌های exe/dll دوباره compress می‌شدند → کند

حل v4.2:
- pack_payload.py v4.2: لاگ دقیق + progress callback + WinError skip + ZIP_STORED برای فایل‌های فشرده + compresslevel=1 سریع + encryption chunked 16MB + بدون load کل فایل در RAM
- build_offline_gui.py v4.2: progress واقعی برای payload + لاگ زنده + عدم freeze UI + threading درست

ویژگی‌ها:
- GUI شیک 920x900 با 6 مرحله progress جدا + سرعت + ETA
- DownloadManager سریع با resume
- فایل نهایی: dist/DivarMarketing-Setup-v4.2-Final.exe
"""

from __future__ import annotations

import os
import sys
import shutil
import subprocess
import threading
import time
import traceback
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
INSTALLER_DIR = Path(__file__).resolve().parent
DIST_DIR = ROOT / "dist"
APP_VERSION = "4.2.0-native-fixed"

# ========== Helpers ==========

def _find_python_exe() -> str:
    for cmd in [sys.executable, "python", "python3", "py"]:
        try:
            r = subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                return cmd
        except:
            continue
    return sys.executable or "python"

def _find_pyinstaller_cmd() -> list[str]:
    py = _find_python_exe()
    try:
        r = subprocess.run([py, "-m", "PyInstaller", "--version"], capture_output=True, timeout=10)
        if r.returncode == 0:
            return [py, "-m", "PyInstaller"]
    except:
        pass
    return [py, "-m", "PyInstaller"]

def log_to_file(msg: str):
    try:
        (ROOT / "build-offline.log").open("a", encoding="utf-8").write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except:
        pass

# ========== GUI v4.2 Fixed ==========

def gui_main():
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox, scrolledtext
    except Exception as e:
        err = f"Tkinter not available: {e}"
        print(err)
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, err, "خطا", 0x10)
        except:
            pass
        return 1

    root = tk.Tk()
    root.title(f"Divar Marketing Builder - v{APP_VERSION}")
    # Responsive minimal fix - was 960x900 fixed, now fits any screen
    try:
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
    except:
        sw, sh = 1920, 1080
    if sw <= 1024 or sh <= 768:
        ww, wh = min(900, sw - 20), min(680, sh - 20)
    elif sw <= 1366:
        ww, wh = 880, min(720, sh - 30)
    else:
        ww, wh = 920, 800
    ww = max(720, ww)
    wh = max(580, wh)
    x = max(0, (sw - ww)//2)
    y = max(0, (sh - wh)//2)
    root.geometry(f"{ww}x{wh}+{x}+{y}")
    root.minsize(720, 580)
    root.resizable(True, True)
    root.configure(bg="#f0f4f8")

    style = ttk.Style()
    try:
        style.theme_use("vista")
    except:
        pass
    style.configure("TProgressbar", thickness=20, troughcolor="#e3e8f0", background="#1976d2")
    style.configure("Python.Horizontal.TProgressbar", background="#3776ab", thickness=18)
    style.configure("Chrome.Horizontal.TProgressbar", background="#8e5bd9", thickness=18)
    style.configure("Model.Horizontal.TProgressbar", background="#2e9e5b", thickness=18)
    style.configure("Pack.Horizontal.TProgressbar", background="#e67e22", thickness=20)
    style.configure("Exe.Horizontal.TProgressbar", background="#d9534f", thickness=18)
    style.configure("Setup.Horizontal.TProgressbar", background="#0f2a4a", thickness=20)

    try:
        ico = INSTALLER_DIR / "app.ico"
        if ico.exists():
            root.iconbitmap(default=str(ico))
    except:
        pass

    main_frame = tk.Frame(root, bg="#f0f4f8")
    main_frame.pack(fill="both", expand=True)
    main_frame.columnconfigure(0, weight=1)
    main_frame.rowconfigure(1, weight=1)

    header = tk.Frame(main_frame, bg="#0f2a4a", height=120)
    header.grid(row=0, column=0, sticky="ew")
    header.grid_propagate(False)
    tk.Label(header, text="🏗️ سازنده نصب‌کننده آفلاین کامل v4.2 — FIXED No Freeze", font=("Segoe UI", 15, "bold"), bg="#0f2a4a", fg="white").pack(anchor="w", padx=20, pady=(12,0))
    tk.Label(header, text=f"Divar Marketing v{APP_VERSION} — یک فایل تکی رمز شده — بدون گیر کردن — با لاگ دقیق", font=("Segoe UI", 10, "bold"), bg="#0f2a4a", fg="#8ec0f0").pack(anchor="w", padx=20)
    tk.Label(header, text="✅ FIXED: بسته‌بندی با لاگ دقیق + WinError هندل + ZIP_STORED سریع + chunked encryption 16MB + بدون load RAM", font=("Segoe UI", 9), bg="#0f2a4a", fg="#a78bfa").pack(anchor="w", padx=20)
    tk.Label(header, text="Python + Chromium + مدل تیرا + payload.zip.enc + Setup.exe — قابل ارسال به هر سیستم — بدون کنسول سیاه", font=("Segoe UI", 8), bg="#0f2a4a", fg="#6b7a90").pack(anchor="w", padx=20, pady=(0,5))

    content = tk.Frame(main_frame, bg="white")
    content.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
    content.columnconfigure(0, weight=1)
    content.rowconfigure(2, weight=1)

    # Settings
    settings_frame = tk.LabelFrame(content, text="⚙️ تنظیمات ساخت v4.2 FIXED", font=("Segoe UI", 10, "bold"), bg="white", fg="#0f2a4a", padx=15, pady=10)
    settings_frame.grid(row=0, column=0, sticky="ew", pady=(0,10))
    settings_frame.columnconfigure(3, weight=1)

    tk.Label(settings_frame, text="نسخه:", font=("Segoe UI", 9), bg="white").grid(row=0, column=0, sticky="w", padx=5, pady=3)
    version_var = tk.StringVar(value=APP_VERSION)
    tk.Entry(settings_frame, textvariable=version_var, font=("Consolas", 9), width=22).grid(row=0, column=1, sticky="w", padx=5, pady=3)

    tk.Label(settings_frame, text="حالت:", font=("Segoe UI", 9), bg="white").grid(row=0, column=2, sticky="w", padx=15, pady=3)
    mode_var = tk.StringVar(value="offline_full")
    ttk.Combobox(settings_frame, textvariable=mode_var, values=["offline_full (پیشنهاد) — شامل کرومیوم+مدل", "online — دانلود در نصب", "light — فقط سورس"], width=45, state="readonly").grid(row=0, column=3, sticky="ew", padx=5, pady=3)

    include_chrome_var = tk.BooleanVar(value=False)  # پیش‌فرض خاموش برای سرعت — کاربر اگر خواست روشن کند
    include_model_var = tk.BooleanVar(value=False)
    encrypt_var = tk.BooleanVar(value=True)
    
    tk.Checkbutton(settings_frame, text="🌐 شامل کرومیوم (~200MB) — کندتر ولی آفلاین کامل", variable=include_chrome_var, bg="white", font=("Segoe UI", 9)).grid(row=1, column=0, columnspan=2, sticky="w", padx=5, pady=3)
    tk.Checkbutton(settings_frame, text="🧠 شامل مدل تیرا (~100MB) — کندتر", variable=include_model_var, bg="white", font=("Segoe UI", 9)).grid(row=1, column=2, columnspan=2, sticky="w", padx=15, pady=3)
    tk.Checkbutton(settings_frame, text="🔐 رمزنگاری chunked (پیشنهاد)", variable=encrypt_var, bg="white", font=("Segoe UI", 9, "bold")).grid(row=2, column=0, columnspan=2, sticky="w", padx=5, pady=3)
    tk.Label(settings_frame, text="💡 برای تست سریع: تیک کرومیوم و مدل را بردارید — بعداً با DownloadManager دانلود می‌شود", font=("Segoe UI", 8), bg="white", fg="#e67e22").grid(row=2, column=2, columnspan=2, sticky="w", padx=15, pady=3)

    # Progress 6 steps
    progress_frame = tk.LabelFrame(content, text="📊 پیشرفت ساخت — 6 مرحله با لاگ دقیق — FIXED No Freeze", font=("Segoe UI", 10, "bold"), bg="white", fg="#0f2a4a", padx=15, pady=10)
    progress_frame.grid(row=1, column=0, sticky="ew", pady=5)
    progress_frame.columnconfigure(1, weight=1)

    bars = {}
    steps = [
        ("python", "🐍 Python & محیط", "Python.Horizontal.TProgressbar"),
        ("chrome", "🌐 Chromium", "Chrome.Horizontal.TProgressbar"),
        ("model", "🧠 مدل تیرا", "Model.Horizontal.TProgressbar"),
        ("payload", "📦 بسته‌بندی payload.zip — FIXED با لاگ دقیق", "Pack.Horizontal.TProgressbar"),
        ("exe", "⚙️ DivarMarketing.exe نیتیو", "Exe.Horizontal.TProgressbar"),
        ("setup", "🎁 Setup.exe نهایی — Wizard", "Setup.Horizontal.TProgressbar"),
    ]
    for idx, (key, label, sty) in enumerate(steps):
        lbl = tk.Label(progress_frame, text=f"{label}: در انتظار...", font=("Segoe UI", 9), bg="white", fg="#334", anchor="w")
        lbl.grid(row=idx*2, column=0, columnspan=3, sticky="ew", pady=(8,0))
        bar = ttk.Progressbar(progress_frame, length=700, mode="determinate", maximum=100, style=sty)
        bar.grid(row=idx*2+1, column=0, columnspan=2, sticky="ew", padx=(0,10), pady=2)
        pct_lbl = tk.Label(progress_frame, text="0%", font=("Consolas", 9, "bold"), bg="white", width=6)
        pct_lbl.grid(row=idx*2+1, column=2, sticky="e")
        bars[key] = (lbl, bar, pct_lbl)

    overall_frame = tk.Frame(progress_frame, bg="white")
    overall_frame.grid(row=len(steps)*2, column=0, columnspan=3, sticky="ew", pady=(15,0))
    overall_frame.columnconfigure(1, weight=1)
    tk.Label(overall_frame, text="📈 کل:", font=("Segoe UI", 10, "bold"), bg="white").grid(row=0, column=0, sticky="w")
    overall_bar = ttk.Progressbar(overall_frame, length=500, mode="determinate", maximum=100)
    overall_bar.grid(row=0, column=1, sticky="ew", padx=10)
    overall_pct = tk.Label(overall_frame, text="0%", font=("Consolas", 10, "bold"), bg="white")
    overall_pct.grid(row=0, column=2, sticky="e")

    # Log
    log_frame = tk.LabelFrame(content, text="📝 لاگ ساخت دقیق — هر فایل لاگ می‌شود — اگر گیر کرد دلیل مشخص است", font=("Segoe UI", 9, "bold"), bg="white", padx=5, pady=5)
    log_frame.grid(row=2, column=0, sticky="nsew", pady=5)
    log_frame.columnconfigure(0, weight=1)
    log_frame.rowconfigure(0, weight=1)
    
    logbox = scrolledtext.ScrolledText(log_frame, height=16, font=("Consolas", 8), bg="#1a202c", fg="#e2e8f0", wrap="word")
    logbox.grid(row=0, column=0, sticky="nsew")

    def log(msg: str):
        def _():
            logbox.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            logbox.see("end")
        try:
            root.after(0, _)
        except:
            pass
        log_to_file(msg)
        print(msg)

    def set_progress(key: str, pct: int, text: str, speed: str = "—"):
        def _():
            if key in bars:
                lbl, bar, pct_lbl = bars[key]
                lbl.configure(text=text if speed=="—" else f"{text} | {speed}")
                bar["value"] = pct
                pct_lbl.configure(text=f"{pct}%")
            total = sum(b[1]["value"] for b in bars.values()) / len(bars)
            overall_bar["value"] = total
            overall_pct.configure(text=f"{int(total)}%")
        try:
            root.after(0, _)
        except:
            pass

    bottom_frame = tk.Frame(main_frame, bg="#e8eef7", height=75)
    bottom_frame.grid(row=2, column=0, sticky="ew")
    bottom_frame.grid_propagate(False)
    bottom_frame.columnconfigure(0, weight=1)

    status_var = tk.StringVar(value="✅ آماده ساخت v4.2 FIXED — بدون گیر کردن — با لاگ دقیق — دکمه زیر را بزنید")
    tk.Label(bottom_frame, textvariable=status_var, font=("Segoe UI", 10, "bold"), bg="#e8eef7", fg="#0f2a4a").grid(row=0, column=0, sticky="w", padx=20, pady=10)

    def build_process():
        try:
            status_var.set("🚀 در حال ساخت v4.2 FIXED...")
            log(f"🏗️ شروع ساخت v{version_var.get()} — حالت: {mode_var.get()} — FIXED No Freeze")
            log(f"📁 ROOT: {ROOT}")
            log(f"📁 DIST: {DIST_DIR}")
            log(f"⚙️ تنظیمات: chrome={include_chrome_var.get()} model={include_model_var.get()} encrypt={encrypt_var.get()}")

            # Step 1: Python
            set_progress("python", 10, "🐍 Python & محیط: بررسی...", "—")
            py_exe = _find_python_exe()
            log(f"🐍 Python: {py_exe}")
            try:
                r = subprocess.run([py_exe, "--version"], capture_output=True, text=True, timeout=10)
                ver = r.stdout.strip() or r.stderr.strip()
                log(f"✅ {ver}")
                set_progress("python", 50, f"🐍 Python: {ver} — نصب ابزار...", "—")
                subprocess.run([py_exe, "-m", "pip", "install", "--upgrade", "pip", "--disable-pip-version-check", "--progress-bar", "off"], capture_output=True, timeout=120)
                subprocess.run([py_exe, "-m", "pip", "install", "--disable-pip-version-check", "--progress-bar", "off", "pyinstaller", "requests", "tqdm"], capture_output=True, timeout=180)
                log("✅ ابزار ساخت نصب شد")
            except Exception as e:
                log(f"❌ Python: {e}")
                set_progress("python", 0, f"🐍 خطا: {e}", "—")
                return
            set_progress("python", 100, "🐍 Python: آماده ✅", "—")

            # Step 2: Chromium — skip if not requested for speed
            set_progress("chrome", 5, "🌐 Chromium: بررسی...", "—")
            if include_chrome_var.get():
                log("🌐 Chromium — بررسی...")
                try:
                    local_appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
                    chrome_path = Path(local_appdata) / "DivarMarketing" / "app-chromium"
                    if chrome_path.exists() and any(chrome_path.iterdir()):
                        size = sum(f.stat().st_size for f in chrome_path.rglob("*") if f.is_file()) // 1024 // 1024
                        log(f"✅ Chromium محلی: {chrome_path} ({size}MB)")
                        set_progress("chrome", 100, f"🌐 Chromium: آماده ✅ {size}MB", "—")
                    else:
                        log("📥 Chromium محلی نیست — در نصب‌کننده دانلود می‌شود")
                        set_progress("chrome", 30, "🌐 Chromium: نیست — در نصب دانلود می‌شود", "—")
                except Exception as e:
                    log(f"❌ Chromium: {e}")
                    set_progress("chrome", 0, f"🌐 خطا: {e}", "—")
            else:
                set_progress("chrome", 100, "🌐 Chromium: رد شد (سریع) — در نصب دانلود می‌شود", "—")
                log("⏭️ Chromium رد شد برای سرعت — در نصب با DownloadManager دانلود می‌شود")

            # Step 3: Model
            set_progress("model", 5, "🧠 مدل تیرا: بررسی...", "—")
            if include_model_var.get():
                try:
                    local_appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
                    mp = Path(local_appdata) / "DivarMarketing" / "app" / "nlu-model"
                    if mp.exists() and any(mp.iterdir()):
                        size = sum(f.stat().st_size for f in mp.rglob("*") if f.is_file()) // 1024 // 1024
                        log(f"✅ مدل محلی: {mp} ({size}MB)")
                        set_progress("model", 100, f"🧠 مدل: آماده ✅ {size}MB", "—")
                    else:
                        log("📥 مدل محلی نیست — fallback")
                        set_progress("model", 50, "🧠 مدل: نیست — fallback", "—")
                except Exception as e:
                    log(f"❌ Model: {e}")
                    set_progress("model", 0, f"🧠 خطا: {e}", "—")
            else:
                set_progress("model", 100, "🧠 مدل: رد شد (سریع) — fallback هوشمند", "—")
                log("⏭️ مدل رد شد برای سرعت")

            # Step 4: Payload — FIXED v4.2
            set_progress("payload", 2, "📦 payload.zip: شروع بسته‌بندی FIXED...", "—")
            log("📦 بسته‌بندی v4.2 FIXED — بدون freeze — با لاگ دقیق هر فایل")
            try:
                sys.path.insert(0, str(ROOT))
                from installer.pack_payload import pack
                payload_zip = INSTALLER_DIR / "payload.zip"
                payload_enc = INSTALLER_DIR / "payload.zip.enc"
                for p in [payload_zip, payload_enc]:
                    if p.exists():
                        try:
                            p.unlink()
                            log(f"🗑️ حذف قبلی: {p.name}")
                        except Exception as e:
                            log(f"⚠️ حذف {p.name} نشد: {e}")

                include_chrome = include_chrome_var.get() and "offline_full" in mode_var.get()
                include_model = include_model_var.get() and "offline_full" in mode_var.get()
                encrypt = encrypt_var.get()

                log(f"📦 Pack v4.2: chrome={include_chrome} model={include_model} encrypt={encrypt}")
                log("📦 ویژگی‌های v4.2: ZIP_STORED برای exe/dll/png + compresslevel=1 سریع + chunked encryption 16MB + WinError هندل")

                def pack_log(msg: str):
                    log(f"[Pack] {msg}")

                def pack_prog(pct: int, text: str):
                    set_progress("payload", 5 + int(pct*0.90), f"📦 {text}", "—")

                # v4.2 signature with log_cb and progress_cb
                result = pack(dest=payload_zip, include_chromium=include_chrome, include_model=include_model,
                              encrypt=encrypt, log_cb=pack_log, progress_cb=pack_prog)

                if result.exists():
                    size_mb = result.stat().st_size // 1024 // 1024
                    log(f"✅ Payload v4.2 ساخته شد: {result} ({size_mb}MB) — بدون freeze — با لاگ دقیق")
                    set_progress("payload", 100, f"📦 payload: آماده ✅ {size_mb}MB — FIXED", "—")
                else:
                    log(f"❌ Payload ساخته نشد")
                    set_progress("payload", 0, "📦 payload خطا", "—")
                    return
            except Exception as e:
                log(f"❌ Payload v4.2 خطا: {e}\n{traceback.format_exc()}")
                set_progress("payload", 0, f"📦 خطا: {e}", "—")
                return

            # Step 5: DivarMarketing.exe
            set_progress("exe", 5, "⚙️ DivarMarketing.exe نیتیو: ساخت...", "—")
            try:
                pyinstaller_cmd = _find_pyinstaller_cmd()
                log(f"⚙️ PyInstaller: {' '.join(pyinstaller_cmd)}")
                DIST_DIR.mkdir(parents=True, exist_ok=True)
                main_py = ROOT / "main.py"
                if not main_py.exists():
                    log(f"❌ main.py نیست: {main_py}")
                    set_progress("exe", 0, "⚙️ main.py نیست", "—")
                    return

                icon_file = INSTALLER_DIR / "app.ico"
                cmd = pyinstaller_cmd + [
                    "--noconfirm", "--clean", "--onefile", "--windowed",
                    "--name", "DivarMarketing",
                    "--distpath", str(DIST_DIR),
                    "--workpath", str(ROOT / "build"),
                    "--specpath", str(ROOT),
                ]
                if icon_file.exists():
                    cmd += ["--icon", str(icon_file)]
                cmd += [
                    "--hidden-import", "marketing_divar.desktop_app",
                    "--hidden-import", "marketing_divar.web.server",
                    "--add-data", f"{ROOT / 'marketing_divar' / 'web' / 'static'};marketing_divar/web/static",
                    str(main_py)
                ]
                log(f"🔨 PyInstaller windowed (بدون کنسول)...")
                proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="ignore")
                for line in proc.stdout:
                    if any(x in line for x in ["Building", "Analyzing", "EXE", "Adding"]):
                        log(f"[PyInstaller] {line.strip()[:150]}")
                        if "Analyzing" in line:
                            set_progress("exe", 20, "⚙️ تحلیل...", "—")
                        elif "Building" in line:
                            set_progress("exe", 60, "⚙️ ساخت...", "—")
                proc.wait(timeout=600)
                if proc.returncode == 0:
                    exe_path = DIST_DIR / "DivarMarketing.exe"
                    if exe_path.exists():
                        size = exe_path.stat().st_size // 1024 // 1024
                        log(f"✅ DivarMarketing.exe نیتیو: {size}MB — بدون کنسول — پنجره ویندوز")
                        set_progress("exe", 100, f"⚙️ آماده ✅ {size}MB — نیتیو ویندوز", "—")
                    else:
                        log("⚠️ exe ساخته نشد — ادامه")
                        set_progress("exe", 50, "⚙️ exe نشد — fallback", "—")
                else:
                    log(f"⚠️ PyInstaller کد {proc.returncode}")
                    set_progress("exe", 50, "⚙️ fallback", "—")
            except Exception as e:
                log(f"⚠️ exe: {e}\n{traceback.format_exc()[:800]}")
                set_progress("exe", 50, "⚙️ خطا ولی ادامه", "—")

            # Step 6: Setup.exe
            set_progress("setup", 5, "🎁 Setup.exe نهایی: بسته‌بندی...", "—")
            try:
                pyinstaller_cmd = _find_pyinstaller_cmd()
                setup_py = INSTALLER_DIR / "setup_app.py"
                log(f"🎁 ساخت Setup.exe از {setup_py}")

                payload_enc = INSTALLER_DIR / "payload.zip.enc"
                payload_zip = INSTALLER_DIR / "payload.zip"
                payload_to_include = payload_enc if payload_enc.exists() else payload_zip
                if not payload_to_include.exists():
                    log("❌ payload نیست!")
                    set_progress("setup", 0, "🎁 payload نیست", "—")
                    return

                size_payload = payload_to_include.stat().st_size // 1024 // 1024
                log(f"📦 payload برای Setup: {payload_to_include.name} ({size_payload}MB)")

                icon_file = INSTALLER_DIR / "app.ico"
                cmd = pyinstaller_cmd + [
                    "--noconfirm", "--clean", "--onefile", "--windowed",
                    "--name", f"DivarMarketing-Setup-v{version_var.get()}-Final",
                    "--distpath", str(DIST_DIR),
                    "--workpath", str(ROOT / "build-setup"),
                    "--specpath", str(ROOT),
                    "--add-data", f"{payload_to_include}{os.pathsep}.",
                ]
                if icon_file.exists():
                    cmd += ["--icon", str(icon_file), "--add-data", f"{icon_file}{os.pathsep}."]
                cmd += [str(setup_py)]

                log("🔨 Setup.exe windowed — Wizard 7 مرحله‌ای — بدون کنسول")
                proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="ignore")
                for line in proc.stdout:
                    if any(x in line for x in ["Building", "EXE", "Analyzing"]):
                        log(f"[Setup] {line.strip()[:150]}")
                        if "Analyzing" in line:
                            set_progress("setup", 20, "🎁 تحلیل...", "—")
                        elif "Building" in line:
                            set_progress("setup", 60, "🎁 ساخت Wizard...", "—")
                proc.wait(timeout=600)

                setup_exe = DIST_DIR / f"DivarMarketing-Setup-v{version_var.get()}-Final.exe"
                if setup_exe.exists():
                    size = setup_exe.stat().st_size // 1024 // 1024
                    log(f"🎉 Setup.exe نهایی v4.2 ساخته شد: {setup_exe} ({size}MB)")
                    log(f"📦 یک فایل تکی رمز شده — بدون گیر کردن — با لاگ دقیق — قابل ارسال به هر سیستم")
                    set_progress("setup", 100, f"🎁 آماده ✅ {size}MB — FIXED No Freeze", "—")
                    status_var.set(f"✅ نصب‌کننده v4.2 آماده: {setup_exe.name} ({size}MB) — FIXED")

                    simple = DIST_DIR / "DivarMarketing-Setup.exe"
                    try:
                        shutil.copy2(setup_exe, simple)
                    except:
                        pass

                    def _show_done():
                        messagebox.showinfo("✅ v4.2 FIXED — ساخت کامل شد!",
                            f"🎉 نصب‌کننده v4.2 FIXED ساخته شد!\n\n"
                            f"📁 {setup_exe}\n📦 {size}MB\n\n"
                            f"✅ FIXED No Freeze:\n"
                            f"• بسته‌بندی با لاگ دقیق هر فایل\n"
                            f"• WinError 2/5/32/123/206 هندل با skip\n"
                            f"• ZIP_STORED برای exe/dll/png — سریع\n"
                            f"• compresslevel=1 نه 6 — سریع\n"
                            f"• رمزنگاری chunked 16MB — بدون RAM زیاد\n"
                            f"• بدون گیر کردن — progress واقعی\n"
                            f"• GUI نیتیو ویندوز — بدون کنسول سیاه\n"
                            f"• برنامه اصلی نیتیو — نه مرورگر\n\n"
                            f"برای تست روی Setup.exe دوبار کلیک کنید!")
                    root.after(0, _show_done)
                else:
                    log("❌ Setup.exe ساخته نشد")
                    set_progress("setup", 0, "🎁 نشد", "—")
            except Exception as e:
                log(f"❌ Setup: {e}\n{traceback.format_exc()}")
                set_progress("setup", 0, f"🎁 خطا: {e}", "—")

            log("🏁 پایان ساخت v4.2 FIXED")
            status_var.set("🏁 پایان — dist/ را چک کنید")

        except Exception as e:
            log(f"❌ خطای کلی: {e}\n{traceback.format_exc()}")
            status_var.set(f"❌ خطا: {e}")

    def on_build():
        if messagebox.askyesno("🚀 ساخت نصب‌کننده v4.2 FIXED؟",
                               f"ساخت نصب‌کننده آفلاین کامل v{version_var.get()} FIXED No Freeze؟\n\n"
                               f"• حالت: {mode_var.get()}\n"
                               f"• کرومیوم: {'بله' if include_chrome_var.get() else 'خیر (سریع)'}\n"
                               f"• مدل: {'بله' if include_model_var.get() else 'خیر (سریع)'}\n"
                               f"• رمزنگاری chunked: {'بله' if encrypt_var.get() else 'خیر'}\n"
                               f"• FIXED: لاگ دقیق + WinError هندل + بدون freeze\n\n"
                               f"حجم: 50MB تا 2.5GB\n"
                               f"زمان: 3 تا 15 دقیقه\n\n"
                               f"ادامه؟"):
            threading.Thread(target=build_process, daemon=True).start()

    build_btn = tk.Button(bottom_frame, text="🚀 ایجاد نصب‌کننده الان — v4.2 FIXED No Freeze", font=("Segoe UI", 12, "bold"), bg="#0f2a4a", fg="white", relief="flat", padx=20, pady=12, command=on_build, cursor="hand2")
    build_btn.grid(row=0, column=1, padx=20, pady=12, sticky="e")

    open_dist_btn = tk.Button(bottom_frame, text="📁 dist", font=("Segoe UI", 9), bg="white", relief="flat",
                              command=lambda: os.startfile(str(DIST_DIR)) if sys.platform=="win32" else None)
    open_dist_btn.grid(row=0, column=2, padx=10, pady=12, sticky="e")

    info_frame = tk.Frame(main_frame, bg="#e8eef7", height=28)
    info_frame.grid(row=3, column=0, sticky="ew")
    info_frame.grid_propagate(False)
    tk.Label(info_frame, text=f"Builder v{APP_VERSION} — FIXED No Freeze — لاگ دقیق + WinError هندل + chunked encryption — نیتیو ویندوز", font=("Segoe UI", 8), bg="#e8eef7", fg="#6b7a90").pack(side="left", padx=15, pady=5)

    root.mainloop()
    return 0

if __name__ == "__main__":
    raise SystemExit(gui_main())
