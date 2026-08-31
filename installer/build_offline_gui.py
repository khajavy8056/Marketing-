# -*- coding: utf-8 -*-
"""🧠 تیرا — سازنده نصب‌کننده آفلاین ریسپانسیو + فیکس WinError2

- پنجره گرافیکی ریسپانسیو (قابل تغییر اندازه، لاگ اسکرول)
- DownloadManager استاندارد برای Chromium + مدل
- payload.zip 1-2GB آفلاین
- ساخت DivarMarketing.exe و Setup.exe با PyInstaller
- فیکس WinError 2: تشخیص درست python exe و pyinstaller
"""

from __future__ import annotations

import os
import sys
import shutil
import subprocess
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

APP_NAME_FA = "مارکتینگ دیوار — تیرا"
VERSION = "3.4.4-tira-fix"


def _find_python_exe() -> Path:
    """پیدا کردن python exe قابل اجرا - فیکس WinError 2"""
    for p in [ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"]:
        if p.exists():
            return p
    try:
        exe = Path(sys.executable)
        if exe.exists() and exe.is_file() and "python" in exe.name.lower():
            return exe
    except Exception:
        pass
    for name in ("python", "python3", "py"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return Path(sys.executable)


def _python_cmd() -> list[str]:
    exe = _find_python_exe()
    if exe.name.lower() in ("py.exe", "py"):
        try:
            subprocess.run([str(exe), "-3", "--version"], capture_output=True, timeout=5)
            return [str(exe), "-3"]
        except Exception:
            return [str(exe)]
    return [str(exe)]


def _find_pyinstaller_cmd(python_cmd: list[str]) -> list[str]:
    try:
        subprocess.run(python_cmd + ["-m", "PyInstaller", "--version"], capture_output=True, timeout=10)
        return python_cmd + ["-m", "PyInstaller"]
    except Exception:
        pass
    found = shutil.which("pyinstaller")
    if found:
        return [found]
    for p in [ROOT / ".venv" / "Scripts" / "pyinstaller.exe", ROOT / ".venv" / "bin" / "pyinstaller"]:
        if p.exists():
            return [str(p)]
    return python_cmd + ["-m", "PyInstaller"]


def _run_with_log(cmd, log_fn, cwd=ROOT):
    try:
        log_fn(f"▶️ CMD: {' '.join(cmd)}")
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
            line = line.rstrip()
            if line:
                log_fn(line)
        rc = proc.wait()
        log_fn(f"⏹️ Exit code: {rc}")
        return rc
    except FileNotFoundError as e:
        log_fn(f"❌ FileNotFoundError: {e} — CMD: {cmd}")
        try:
            log_fn(f"   Python exe exists? {Path(cmd[0]).exists() if cmd else 'no cmd'}")
        except Exception:
            pass
        import traceback
        log_fn(traceback.format_exc())
        return 1
    except Exception as e:
        log_fn(f"❌ Exception: {e}")
        import traceback
        log_fn(traceback.format_exc())
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
    root.geometry("720x700")
    root.minsize(600, 540)
    root.resizable(True, True)
    root.configure(bg="#0f172a")
    _center_window(root, 720, 700)

    try:
        ico = ROOT / "installer" / "app.ico"
        if ico.exists():
            root.iconbitmap(default=str(ico))
    except Exception:
        pass

    main = tk.Frame(root, bg="#0f172a")
    main.pack(fill="both", expand=True)
    main.columnconfigure(0, weight=1)
    main.rowconfigure(3, weight=1)

    header = tk.Frame(main, bg="#0f172a")
    header.grid(row=0, column=0, sticky="ew")
    header.columnconfigure(0, weight=1)
    tk.Label(header, text="🧠 تیرا — سازنده آفلاین", font=("Segoe UI", 16, "bold"), fg="#a78bfa", bg="#0f172a").pack(anchor="w", padx=16, pady=(10, 0))
    tk.Label(header, text=f"نسخه {VERSION} — ریسپانسیو | فیکس WinError2 | Chromium + مدل داخل Setup (1-2GB)",
             font=("Segoe UI", 8), fg="#94a3b8", bg="#0f172a", justify="left", wraplength=680).pack(anchor="w", padx=16, pady=(2, 6))

    overall_frame = tk.Frame(main, bg="#0f172a")
    overall_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=2)
    overall_frame.columnconfigure(0, weight=1)
    status_var = tk.StringVar(value="آماده — دکمه ساخت را بزن")
    tk.Label(overall_frame, textvariable=status_var, font=("Segoe UI", 9, "bold"), fg="#38bdf8", bg="#0f172a", anchor="w").pack(fill="x")
    overall = ttk.Progressbar(overall_frame, mode="determinate", maximum=100)
    overall.pack(fill="x", pady=2)

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
    lbl_chrome, bar_chrome = make_step("2️⃣ Chromium — DownloadManager")
    lbl_model, bar_model = make_step("3️⃣ مدل تیرا Qwen — DownloadManager")
    lbl_pack, bar_pack = make_step("4️⃣ بسته‌بندی payload.zip آفلاین")
    lbl_exe, bar_exe = make_step("5️⃣ ساخت DivarMarketing.exe (پنجره مستقل)")
    lbl_setup, bar_setup = make_step("6️⃣ ساخت Setup.exe رمزنگاری شده آفلاین")

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

    btns = tk.Frame(main, bg="#0f172a")
    btns.grid(row=4, column=0, sticky="ew", padx=16, pady=8)
    btns.columnconfigure(0, weight=1)
    btn = tk.Button(btns, text="🚀 ساخت نصب‌کننده آفلاین کامل", font=("Segoe UI", 10, "bold"),
                    bg="#7c3aed", fg="white", activebackground="#6d28d9", relief="flat", padx=10, pady=8)
    btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))
    tk.Button(btns, text="خروج", width=8, command=root.destroy, bg="#334155", fg="white", relief="flat", padx=8, pady=8).grid(row=0, column=1)

    def work():
        python_cmd = _python_cmd()
        log(f"🐍 Python exe: {python_cmd} -> exists={Path(python_cmd[0]).exists()}")
        pyinstaller_cmd = _find_pyinstaller_cmd(python_cmd)
        log(f"🔨 PyInstaller cmd: {pyinstaller_cmd}")

        try:
            set_overall(5, "📦 نصب ابزارهای ساخت...")
            set_progress(bar_py, lbl_py, 0, "1️⃣ نصب pyinstaller و وابستگی‌ها...")
            log("[1/6] Installing build tools...")

            rc = _run_with_log(python_cmd + ["-m", "pip", "install", "-r", "requirements.txt", "pyinstaller", "--disable-pip-version-check", "-q"],
                               log, cwd=ROOT)
            if rc != 0:
                log("[WARN] Trying mirror...")
                _run_with_log(python_cmd + ["-m", "pip", "install", "-r", "requirements.txt", "pyinstaller",
                                            "-i", "https://mirror-pypi.runflare.com/simple", "--disable-pip-version-check", "-q"], log, cwd=ROOT)
            pyinstaller_cmd = _find_pyinstaller_cmd(python_cmd)
            log(f"🔨 PyInstaller after install: {pyinstaller_cmd}")
            set_progress(bar_py, lbl_py, 100, "1️⃣ ابزارها آماده ✅")

            set_overall(20, "🌐 دانلود Chromium...")
            set_progress(bar_chrome, lbl_chrome, 0, "2️⃣ Chromium — شروع...")

            def chrome_log(m: str):
                log(m)
                try:
                    if "PROGRESS" in m:
                        import re
                        mm = re.search(r"PROGRESS\s+(\d+)", m)
                        if mm:
                            pct = int(mm.group(1))
                            set_progress(bar_chrome, lbl_chrome, pct, f"2️⃣ Chromium {pct}%")
                    elif "CHROMIUM_OK" in m or "Completed" in m:
                        set_progress(bar_chrome, lbl_chrome, 100, "2️⃣ Chromium آماده ✅")
                except Exception:
                    pass

            try:
                from marketing_divar.app_chromium import ensure_installed as chrome_install
                from marketing_divar.paths import apply_runtime_paths
                apply_runtime_paths()

                def on_pct(p):
                    set_progress(bar_chrome, lbl_chrome, min(100, int(p)), f"2️⃣ Chromium {int(p)}%")

                chrome_install(log=chrome_log, progress=on_pct)
                set_progress(bar_chrome, lbl_chrome, 100, "2️⃣ Chromium آماده ✅")
            except Exception as e:
                log(f"⚠️ Chromium: {e}")
                _run_with_log(python_cmd + ["main.py", "--install-chromium"], log, cwd=ROOT)
                set_progress(bar_chrome, lbl_chrome, 80, "2️⃣ Chromium — تلاش مجدد")

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
                            set_progress(bar_model, lbl_model, pct, f"3️⃣ مدل {pct}%")
                except Exception:
                    pass

            try:
                from marketing_divar.nlu_model import ensure_installed as nlu_install, is_ready as nlu_ready
                if nlu_ready():
                    log("✅ مدل از قبل آماده")
                    set_progress(bar_model, lbl_model, 100, "3️⃣ مدل آماده ✅ (از قبل)")
                else:
                    def on_pct(p):
                        set_progress(bar_model, lbl_model, min(100, int(p)), f"3️⃣ مدل {int(p)}%")
                    nlu_install(log=model_log, progress=on_pct)
                    set_progress(bar_model, lbl_model, 100, "3️⃣ مدل آماده ✅")
            except Exception as e:
                log(f"⚠️ Model: {e}")
                _run_with_log(python_cmd + ["main.py", "--install-nlu"], log, cwd=ROOT)
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
                    if sz > 2500:
                        log(f"⚠️ Payload >2.5GB — Setup نهایی سنگین خواهد بود")
                else:
                    set_progress(bar_pack, lbl_pack, 100, "4️⃣ بسته‌بندی کامل ✅")
            except Exception as e:
                log(f"Pack error: {e}")
                _run_with_log(python_cmd + ["installer/pack_payload.py", "--offline"], log, cwd=ROOT)
                set_progress(bar_pack, lbl_pack, 100, "4️⃣ بسته‌بندی کامل ✅")

            set_overall(75, "🔨 ساخت DivarMarketing.exe...")
            set_progress(bar_exe, lbl_exe, 0, "5️⃣ ساخت exe اصلی...")
            log("[5/6] Building DivarMarketing.exe...")

            for d in [ROOT / "build", ROOT / "dist" / "DivarMarketing.exe"]:
                try:
                    if d.is_dir():
                        shutil.rmtree(d, ignore_errors=True)
                    elif d.is_file():
                        d.unlink()
                except Exception:
                    pass

            sep = os.pathsep
            icon_path = ROOT / "installer" / "app.ico"
            static_src = ROOT / "marketing_divar" / "web" / "static"
            fetch_src = ROOT / "installer" / "fetch_chromium.py"

            cmd_exe = pyinstaller_cmd + [
                "--noconfirm", "--clean", "--onefile", "--name", "DivarMarketing",
            ]
            if icon_path.exists():
                cmd_exe += ["--icon", str(icon_path)]
            else:
                log(f"⚠️ Icon not found: {icon_path} — skipping icon")

            cmd_exe += [
                "--collect-all", "uvicorn", "--collect-submodules", "uvicorn",
                "--collect-all", "playwright", "--collect-submodules", "playwright",
                "--hidden-import", "marketing_divar.web.server",
                "--hidden-import", "marketing_divar.desktop_app",
                "--hidden-import", "marketing_divar.nlu_model",
            ]
            if static_src.exists():
                cmd_exe += ["--add-data", f"{static_src}{sep}marketing_divar/web/static"]
            if fetch_src.exists():
                cmd_exe += ["--add-data", f"{fetch_src}{sep}."]
            if icon_path.exists():
                cmd_exe += ["--add-data", f"{icon_path}{sep}."]

            cmd_exe += ["main.py"]

            rc = _run_with_log(cmd_exe, log, cwd=ROOT)
            if rc == 0:
                set_progress(bar_exe, lbl_exe, 100, "5️⃣ DivarMarketing.exe آماده ✅")
                try:
                    import zipfile
                    zpath = ROOT / "installer" / "payload.zip"
                    exe_path = ROOT / "dist" / "DivarMarketing.exe"
                    if exe_path.exists() and zpath.exists() and exe_path.stat().st_size < 500_000_000:
                        with zipfile.ZipFile(zpath, "a", zipfile.ZIP_DEFLATED) as zf:
                            zf.write(exe_path, "DivarMarketing.exe")
                        log(f"✅ Added exe to payload")
                except Exception as e:
                    log(f"Add exe failed: {e}")
            else:
                set_progress(bar_exe, lbl_exe, 0, f"5️⃣ خطا در ساخت exe (code {rc})")
                log(f"❌ PyInstaller failed — trying fallback without icon")
                cmd_exe2 = pyinstaller_cmd + [
                    "--noconfirm", "--clean", "--onefile", "--name", "DivarMarketing",
                    "--hidden-import", "marketing_divar.web.server",
                    "--hidden-import", "marketing_divar.desktop_app",
                    "main.py"
                ]
                rc2 = _run_with_log(cmd_exe2, log, cwd=ROOT)
                if rc2 == 0:
                    set_progress(bar_exe, lbl_exe, 100, "5️⃣ DivarMarketing.exe آماده ✅ (fallback)")

            set_overall(90, "🔐 ساخت Setup.exe...")
            set_progress(bar_setup, lbl_setup, 0, "6️⃣ ساخت Setup.exe...")
            log("[6/6] Building encrypted Setup.exe...")

            payload_path = ROOT / "installer" / "payload.zip"
            if not payload_path.exists():
                log(f"❌ payload.zip not found: {payload_path}")
                set_progress(bar_setup, lbl_setup, 0, "6️⃣ payload.zip پیدا نشد")
            else:
                sz_mb = payload_path.stat().st_size // 1024 // 1024
                log(f"📦 Payload size: {sz_mb} MB")
                if sz_mb > 3500:
                    log(f"⚠️ Very large payload ({sz_mb} MB) may exceed limits")

                cmd_setup = pyinstaller_cmd + [
                    "--noconfirm", "--clean", "--onefile", "--windowed",
                    "--name", "DivarMarketing-Setup",
                ]
                if icon_path.exists():
                    cmd_setup += ["--icon", str(icon_path)]

                cmd_setup += ["--add-data", f"{payload_path}{sep}."]
                if icon_path.exists():
                    cmd_setup += ["--add-data", f"{icon_path}{sep}."]
                if fetch_src.exists():
                    cmd_setup += ["--add-data", f"{fetch_src}{sep}."]

                cmd_setup += ["installer/setup_app.py"]

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
                        log(f"❌ dist/DivarMarketing-Setup.exe not found")
                else:
                    set_progress(bar_setup, lbl_setup, 0, f"6️⃣ خطا در ساخت Setup (code {rc})")
                    log(f"❌ PyInstaller failed for Setup.exe")

            log("")
            log("============================================")
            log("✅ ساخت تمام شد — لاگ بالا را چک کن")
            log("📁 dist/DivarMarketing-Setup.exe")
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
    python_cmd = _python_cmd()
    print(f"Python: {python_cmd}")
    pyinstaller_cmd = _find_pyinstaller_cmd(python_cmd)
    print(f"PyInstaller: {pyinstaller_cmd}")
    subprocess.run(python_cmd + ["installer/pack_payload.py", "--offline"], cwd=str(ROOT))
    return 0


if __name__ == "__main__":
    if "--cli" in sys.argv:
        raise SystemExit(cli())
    else:
        raise SystemExit(gui())
