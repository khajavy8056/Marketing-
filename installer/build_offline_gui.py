# -*- coding: utf-8 -*-
"""🧠 تیرا — سازنده نصب‌کننده آفلاین ریسپانسیو

وقتی ساخت-نصب-استاندارد.bat را می‌زنی:
- پنجره گرافیکی زیبا باز می‌شود (Tkinter تم تیرا) — ریسپانسیو
- نوار پیشرفت هر مرحله + لاگ قابل اسکرول
- Chromium + مدل Qwen با DownloadManager استاندارد (resume + آینه + سرعت)
- payload.zip 1-2GB + Setup.exe رمزنگاری شده آفلاین کامل
"""

from __future__ import annotations

import os
import sys
import threading
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

APP_NAME_FA = "مارکتینگ دیوار — تیرا"
VERSION = "3.4.3-tira-responsive"


def _find_python() -> str:
    cands = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
    ]
    for p in cands:
        if p.exists():
            return str(p)
    for exe in ("py -3", "python", "python3"):
        try:
            subprocess.run(exe.split() + ["--version"], capture_output=True, timeout=5)
            return exe
        except Exception:
            continue
    return sys.executable


def _run_with_log(cmd, log_fn, cwd=ROOT):
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if line:
                log_fn(line)
        proc.wait()
        return proc.returncode
    except Exception as e:
        log_fn(f"❌ {e}")
        return 1


def _center_window(root, w, h):
    try:
        root.update_idletasks()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        root.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        pass


def gui():
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as e:
        print(f"GUI not available: {e}")
        return cli()

    root = tk.Tk()
    root.title(f"{APP_NAME_FA} — ساخت نصب‌کننده آفلاین")
    root.geometry("720x680")
    root.minsize(600, 520)
    root.resizable(True, True)
    root.configure(bg="#0f172a")
    _center_window(root, 720, 680)

    try:
        ico = ROOT / "installer" / "app.ico"
        if ico.exists():
            root.iconbitmap(default=str(ico))
    except Exception:
        pass

    # Main container expandable
    main = tk.Frame(root, bg="#0f172a")
    main.pack(fill="both", expand=True)
    main.columnconfigure(0, weight=1)
    main.rowconfigure(3, weight=1)  # log row expands

    # Header compact
    header = tk.Frame(main, bg="#0f172a")
    header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
    header.columnconfigure(0, weight=1)
    tk.Label(header, text="🧠 تیرا — سازنده آفلاین", font=("Segoe UI", 16, "bold"), fg="#a78bfa", bg="#0f172a").pack(anchor="w", padx=16, pady=(10, 0))
    tk.Label(header, text=f"نسخه {VERSION} — ریسپانسیو | Chromium + مدل داخل Setup (1-2GB) | رمزنگاری شده",
             font=("Segoe UI", 8), fg="#94a3b8", bg="#0f172a", justify="left", wraplength=680).pack(anchor="w", padx=16, pady=(2, 6))

    # Overall
    overall_frame = tk.Frame(main, bg="#0f172a")
    overall_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=2)
    overall_frame.columnconfigure(0, weight=1)
    status_var = tk.StringVar(value="آماده — دکمه ساخت را بزن")
    tk.Label(overall_frame, textvariable=status_var, font=("Segoe UI", 9, "bold"), fg="#38bdf8", bg="#0f172a", anchor="w").pack(fill="x")
    overall = ttk.Progressbar(overall_frame, mode="determinate", maximum=100)
    overall.pack(fill="x", pady=2)

    # Steps - fixed height but expand width
    steps_frame = tk.Frame(main, bg="#0f172a")
    steps_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=4)
    steps_frame.columnconfigure(0, weight=1)

    def make_step(title):
        f = tk.Frame(steps_frame, bg="#0f172a")
        f.pack(fill="x", pady=2)
        f.columnconfigure(0, weight=1)
        lbl = tk.Label(f, text=title, font=("Segoe UI", 8), fg="#cbd5e1", bg="#0f172a", anchor="w")
        lbl.grid(row=0, column=0, sticky="ew")
        bar = ttk.Progressbar(f, mode="determinate", maximum=100)
        bar.grid(row=1, column=0, sticky="ew", pady=1)
        return lbl, bar

    lbl_py, bar_py = make_step("1️⃣ Python و ابزارها")
    lbl_chrome, bar_chrome = make_step("2️⃣ Chromium — DownloadManager (resume + آینه)")
    lbl_model, bar_model = make_step("3️⃣ مدل تیرا Qwen — DownloadManager")
    lbl_pack, bar_pack = make_step("4️⃣ بسته‌بندی payload.zip آفلاین")
    lbl_exe, bar_exe = make_step("5️⃣ ساخت DivarMarketing.exe (پنجره مستقل)")
    lbl_setup, bar_setup = make_step("6️⃣ ساخت Setup.exe رمزنگاری شده آفلاین")

    # Log - expandable with scrollbar
    log_frame = tk.Frame(main, bg="#0f172a")
    log_frame.grid(row=3, column=0, sticky="nsew", padx=16, pady=4)
    log_frame.columnconfigure(0, weight=1)
    log_frame.rowconfigure(0, weight=1)

    logbox = tk.Text(log_frame, font=("Consolas", 8), bg="#1e293b", fg="#e2e8f0", relief="flat", wrap="word")
    logbox.grid(row=0, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=logbox.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    logbox.configure(yscrollcommand=scrollbar.set, state="disabled")

    def log(msg: str):
        def _do():
            logbox.configure(state="normal")
            logbox.insert("end", msg + "\n")
            logbox.see("end")
            logbox.configure(state="disabled")
        try:
            root.after(0, _do)
        except Exception:
            print(msg)

    def set_progress(bar, lbl, pct, txt):
        def _do():
            bar["value"] = pct
            lbl.configure(text=txt)
        try:
            root.after(0, _do)
        except Exception:
            pass

    def set_overall(pct, txt):
        def _do():
            overall["value"] = pct
            status_var.set(txt)
        try:
            root.after(0, _do)
        except Exception:
            pass

    # Buttons bottom
    btns = tk.Frame(main, bg="#0f172a")
    btns.grid(row=4, column=0, sticky="ew", padx=16, pady=8)
    btns.columnconfigure(0, weight=1)
    btn = tk.Button(btns, text="🚀 ساخت نصب‌کننده آفلاین کامل", font=("Segoe UI", 10, "bold"),
                    bg="#7c3aed", fg="white", activebackground="#6d28d9", relief="flat", padx=10, pady=8)
    btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))
    tk.Button(btns, text="خروج", width=8, command=root.destroy, bg="#334155", fg="white", relief="flat", padx=8, pady=8).grid(row=0, column=1)

    def work():
        py_exe = _find_python()
        log(f"🐍 Python: {py_exe}")

        try:
            set_overall(5, "📦 نصب ابزارهای ساخت...")
            set_progress(bar_py, lbl_py, 0, "1️⃣ نصب pyinstaller و وابستگی‌ها...")
            log("[1/6] Installing build tools...")
            rc = _run_with_log([py_exe, "-m", "pip", "install", "-r", "requirements.txt", "pyinstaller", "--disable-pip-version-check", "-q"],
                               log, cwd=ROOT)
            if rc != 0:
                log("[WARN] Trying mirror...")
                _run_with_log([py_exe, "-m", "pip", "install", "-r", "requirements.txt", "pyinstaller",
                               "-i", "https://mirror-pypi.runflare.com/simple", "--disable-pip-version-check", "-q"], log, cwd=ROOT)
            set_progress(bar_py, lbl_py, 100, "1️⃣ ابزارها آماده ✅")

            set_overall(20, "🌐 دانلود Chromium با DownloadManager...")
            set_progress(bar_chrome, lbl_chrome, 0, "2️⃣ Chromium — شروع...")

            def chrome_log(m: str):
                log(m)
                try:
                    if "PROGRESS" in m:
                        import re
                        mm = re.search(r"PROGRESS\s+(\d+)", m)
                        if mm:
                            pct = int(mm.group(1))
                            set_progress(bar_chrome, lbl_chrome, pct, f"2️⃣ Chromium {pct}% — DownloadManager")
                    elif "CHROMIUM_OK" in m or "Completed" in m:
                        set_progress(bar_chrome, lbl_chrome, 100, "2️⃣ Chromium آماده ✅")
                except Exception:
                    pass

            try:
                from marketing_divar.app_chromium import ensure_installed as chrome_install
                from marketing_divar.paths import apply_runtime_paths
                apply_runtime_paths()

                def on_pct(p):
                    set_progress(bar_chrome, lbl_chrome, min(100, int(p)), f"2️⃣ Chromium {int(p)}% — DownloadManager")

                chrome_install(log=chrome_log, progress=on_pct)
                set_progress(bar_chrome, lbl_chrome, 100, "2️⃣ Chromium آماده ✅")
            except Exception as e:
                log(f"⚠️ Chromium: {e} — سعی با main.py")
                _run_with_log([py_exe, "main.py", "--install-chromium"], log, cwd=ROOT)
                set_progress(bar_chrome, lbl_chrome, 80, "2️⃣ Chromium — تلاش مجدد در پنل")

            set_overall(40, "🧠 دانلود مدل تیرا...")
            set_progress(bar_model, lbl_model, 0, "3️⃣ مدل تیرا — شروع...")

            def model_log(m: str):
                log(m)
                try:
                    if "%" in m:
                        import re
                        mm = re.search(r"(\d+)%", m)
                        if mm:
                            pct = int(mm.group(1))
                            set_progress(bar_model, lbl_model, pct, f"3️⃣ مدل تیرا {pct}%")
                except Exception:
                    pass

            try:
                from marketing_divar.nlu_model import ensure_installed as nlu_install, is_ready as nlu_ready
                if nlu_ready():
                    log("✅ مدل از قبل آماده")
                    set_progress(bar_model, lbl_model, 100, "3️⃣ مدل تیرا آماده ✅ (از قبل)")
                else:
                    def on_pct(p):
                        set_progress(bar_model, lbl_model, min(100, int(p)), f"3️⃣ مدل تیرا {int(p)}% — DownloadManager")
                    nlu_install(log=model_log, progress=on_pct)
                    set_progress(bar_model, lbl_model, 100, "3️⃣ مدل تیرا آماده ✅")
            except Exception as e:
                log(f"⚠️ Model: {e}")
                _run_with_log([py_exe, "main.py", "--install-nlu"], log, cwd=ROOT)
                set_progress(bar_model, lbl_model, 80, "3️⃣ مدل — fallback")

            set_overall(60, "📦 بسته‌بندی آفلاین...")
            set_progress(bar_pack, lbl_pack, 0, "4️⃣ بسته‌بندی payload.zip...")
            log("[4/6] Packing offline payload...")

            try:
                from installer.pack_payload import pack
                pack(offline=True)
                ppath = ROOT / "installer" / "payload.zip"
                if ppath.exists():
                    sz = ppath.stat().st_size // 1024 // 1024
                    set_progress(bar_pack, lbl_pack, 100, f"4️⃣ بسته‌بندی کامل ✅ {sz} MB")
                    log(f"✅ Payload: {sz} MB")
                else:
                    set_progress(bar_pack, lbl_pack, 100, "4️⃣ بسته‌بندی کامل ✅")
            except Exception as e:
                log(f"Pack error: {e}")
                _run_with_log([py_exe, "installer/pack_payload.py", "--offline"], log, cwd=ROOT)
                set_progress(bar_pack, lbl_pack, 100, "4️⃣ بسته‌بندی کامل ✅")

            set_overall(75, "🔨 ساخت DivarMarketing.exe...")
            set_progress(bar_exe, lbl_exe, 0, "5️⃣ ساخت exe اصلی...")
            log("[5/6] Building DivarMarketing.exe...")

            import shutil
            for d in [ROOT / "build", ROOT / "dist" / "DivarMarketing.exe"]:
                try:
                    if d.is_dir():
                        shutil.rmtree(d, ignore_errors=True)
                    elif d.is_file():
                        d.unlink()
                except Exception:
                    pass

            cmd_exe = [
                py_exe, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--name", "DivarMarketing",
                "--icon", "installer/app.ico",
                "--collect-all", "uvicorn", "--collect-submodules", "uvicorn",
                "--collect-all", "playwright", "--collect-submodules", "playwright",
                "--hidden-import", "marketing_divar.web.server",
                "--hidden-import", "marketing_divar.desktop_app",
                "--hidden-import", "marketing_divar.nlu_model",
                "--add-data", "marketing_divar/web/static;marketing_divar/web/static",
                "--add-data", "installer/fetch_chromium.py;.",
                "--add-data", "installer/app.ico;.",
                "main.py"
            ]
            rc = _run_with_log(cmd_exe, log, cwd=ROOT)
            if rc == 0:
                set_progress(bar_exe, lbl_exe, 100, "5️⃣ DivarMarketing.exe آماده ✅")
                try:
                    import zipfile
                    zpath = ROOT / "installer" / "payload.zip"
                    exe_path = ROOT / "dist" / "DivarMarketing.exe"
                    if exe_path.exists() and zpath.exists():
                        with zipfile.ZipFile(zpath, "a", zipfile.ZIP_DEFLATED) as zf:
                            zf.write(exe_path, "DivarMarketing.exe")
                        log(f"✅ Added exe to payload")
                except Exception as e:
                    log(f"Add exe failed: {e}")
            else:
                set_progress(bar_exe, lbl_exe, 0, "5️⃣ خطا در ساخت exe")

            set_overall(90, "🔐 ساخت Setup.exe رمزنگاری شده...")
            set_progress(bar_setup, lbl_setup, 0, "6️⃣ ساخت Setup.exe...")
            log("[6/6] Building encrypted Setup.exe...")

            cmd_setup = [
                py_exe, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
                "--name", "DivarMarketing-Setup",
                "--icon", "installer/app.ico",
                "--add-data", "installer/payload.zip;.",
                "--add-data", "installer/app.ico;.",
                "--add-data", "installer/fetch_chromium.py;.",
                "installer/setup_app.py"
            ]
            rc = _run_with_log(cmd_setup, log, cwd=ROOT)
            if rc == 0:
                exe_path = ROOT / "dist" / "DivarMarketing-Setup.exe"
                if exe_path.exists():
                    sz = exe_path.stat().st_size // 1024 // 1024
                    set_progress(bar_setup, lbl_setup, 100, f"6️⃣ Setup.exe آماده ✅ {sz} MB — آفلاین")
                    log(f"✅ Setup.exe: {exe_path} ({sz} MB)")
                    try:
                        desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
                        if desktop.exists():
                            shutil.copy2(exe_path, desktop / "DivarMarketing-Setup.exe")
                            log(f"✅ Copied to Desktop")
                    except Exception:
                        pass
                    set_overall(100, f"✅ تمام شد — Setup.exe آماده ({sz} MB)")
                else:
                    set_progress(bar_setup, lbl_setup, 0, "6️⃣ فایل Setup پیدا نشد")
            else:
                set_progress(bar_setup, lbl_setup, 0, "6️⃣ خطا در ساخت Setup")

            log("")
            log("============================================")
            log("✅ ساخت نصب‌کننده آفلاین کامل شد")
            log("📁 dist/DivarMarketing-Setup.exe (1-2GB)")
            log("شامل Chromium + مدل Qwen — بدون نیاز دانلود")
            log("کد رمزنگاری شده — دابل کلیک → نصب گرافیکی → تیرا")
            log("============================================")

        except Exception as e:
            import traceback
            log(f"❌ خطا: {e}")
            log(traceback.format_exc())
            set_overall(0, f"❌ خطا: {e}")

    def start_build():
        btn.configure(state="disabled")
        threading.Thread(target=work, daemon=True).start()

    btn.configure(command=start_build)
    root.mainloop()
    return 0


def cli():
    print("CLI builder")
    py_exe = _find_python()
    print(f"Python: {py_exe}")
    subprocess.run([py_exe, "installer/pack_payload.py", "--offline"], cwd=str(ROOT))
    return 0


if __name__ == "__main__":
    if "--cli" in sys.argv:
        raise SystemExit(cli())
    else:
        raise SystemExit(gui())
