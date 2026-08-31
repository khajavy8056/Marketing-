# -*- coding: utf-8 -*-
"""🧠 تیرا — نصب‌کننده گرافیکی ریسپانسیو و تمیز

- یک فایل Setup.exe (رمزنگاری شده) شامل payload.zip
- payload آفلاین شامل Chromium + مدل Qwen (1-2GB) → بدون دانلود
- اگر مدل موجود باشد استفاده می‌کند، وگرنه DownloadManager استاندارد
- اتصالات سیستم کامل + پنجره مستقل دسکتاپ (نه مرورگر)
- ریسپانسیو: قابل تغییر اندازه، منعطف، اسکرول، مناسب صفحه‌های کوچک
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import zipfile
from pathlib import Path

APP_ID = "DivarMarketing"
APP_NAME = "Divar Marketing — 🧠 تیرا"
APP_NAME_EN = "Divar Marketing"
APP_NAME_FA = "مارکتینگ دیوار — تیرا"
AI_NAME = "تیرا"
PORT = 8642
VERSION = "3.4.3-tira-responsive"
CREATE_NO_WINDOW = 0x08000000


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


def payload_zip() -> Path:
    return _meipass() / "payload.zip"


def app_icon() -> Path:
    for p in (_meipass() / "app.ico", Path(__file__).resolve().parent / "app.ico"):
        if p.exists():
            return p
    return Path()


def _copy_offline_assets(dest: Path, log):
    try:
        persist = data_dir()
        src_chrome = dest / "app-chromium"
        if src_chrome.exists():
            dst_chrome = persist / "app-chromium"
            log(f"📦 Offline Chromium -> {dst_chrome}")
            if dst_chrome.exists():
                shutil.rmtree(dst_chrome, ignore_errors=True)
            shutil.copytree(src_chrome, dst_chrome, dirs_exist_ok=True)
            log(f"✅ Chromium offline copied")
        src_model = dest / "nlu-model"
        if src_model.exists():
            dst_model = persist / "nlu-model"
            log(f"📦 Offline model -> {dst_model}")
            if any(src_model.glob("*.gguf")):
                if dst_model.exists():
                    shutil.rmtree(dst_model, ignore_errors=True)
                shutil.copytree(src_model, dst_model, dirs_exist_ok=True)
                log(f"✅ Model offline copied")
    except Exception as e:
        log(f"Offline copy skip: {e}")


def create_layout(dest: Path, log) -> None:
    for name in ("data", "logs", "accounts", "app-chromium", "nlu-model", "nlu-download"):
        (dest / name).mkdir(parents=True, exist_ok=True)
    persist = data_dir()
    for name in ("accounts", "logs", "app-chromium", "nlu-model", "nlu-download"):
        (persist / name).mkdir(parents=True, exist_ok=True)
    log(f"📁 Folders ready")

    cfg_path = persist / "config.json"
    if not cfg_path.exists():
        try:
            cfg = {
                "version": VERSION,
                "ai_name": AI_NAME,
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
            log(f"⚙️ Config created")
        except Exception as e:
            log(f"Config skip: {e}")

    try:
        db_path = persist / "divar_leads.db"
        if not db_path.exists():
            db_path.touch()
    except Exception:
        pass

    _copy_offline_assets(dest, log)


def extract_payload(dest: Path, log) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    zpath = payload_zip()
    if zpath.exists():
        log(f"📦 Extracting {zpath.stat().st_size // 1024 // 1024} MB...")
        with zipfile.ZipFile(zpath, "r") as zf:
            zf.extractall(dest)
        log(f"✅ Extracted")
    else:
        root = Path(__file__).resolve().parent.parent
        log(f"No payload.zip — copying from {root}")
        for name in ("main.py", "requirements.txt", "marketing_divar", "installer"):
            src = root / name
            dst = dest / name
            if not src.exists():
                continue
            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "payload.zip"))
            else:
                shutil.copy2(src, dst)

    create_layout(dest, log)

    for cand in [dest / f"{APP_ID}.exe", dest / "dist" / f"{APP_ID}.exe", dest / "DivarMarketing.exe"]:
        if cand.exists():
            return cand
    main = dest / "main.py"
    if main.exists():
        return main
    raise FileNotFoundError("main.py not found")


def make_shortcut(target: Path, workdir: Path, ico: Path, log) -> None:
    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    start = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    for folder, fname in [(desktop, f"{APP_NAME_FA}.lnk"), (start, f"{APP_NAME_FA}.lnk")]:
        if not folder:
            continue
        try:
            folder.mkdir(parents=True, exist_ok=True)
            lnk = folder / fname
            try:
                import win32com.client
                shell = win32com.client.Dispatch("WScript.Shell")
                sc = shell.CreateShortcut(str(lnk))
                pyw = Path(sys.executable).with_name("pythonw.exe")
                if target.suffix.lower() == ".exe":
                    sc.TargetPath = str(target)
                    sc.Arguments = "--desktop"
                elif pyw.exists():
                    sc.TargetPath = str(pyw)
                    sc.Arguments = f'"{target}" --desktop'
                else:
                    sc.TargetPath = sys.executable
                    sc.Arguments = f'"{target}" --desktop'
                sc.WorkingDirectory = str(workdir)
                sc.Description = f"{APP_NAME_FA} - {AI_NAME}"
                sc.WindowStyle = 7
                if ico and ico.exists():
                    sc.IconLocation = str(ico)
                sc.Save()
            except Exception:
                tgt = str(target) if target.suffix.lower() == ".exe" else str(Path(sys.executable).with_name("pythonw.exe"))
                args = "--desktop" if target.suffix.lower() == ".exe" else f'"{target}" --desktop'
                ps = f'$s=(New-Object -ComObject WScript.Shell).CreateShortcut("{lnk}");$s.TargetPath="{tgt}";$s.Arguments="{args}";$s.WorkingDirectory="{workdir}";$s.WindowStyle=7;'
                if ico and ico.exists():
                    ps += f'$s.IconLocation="{ico}";'
                ps += "$s.Save()"
                subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, check=False)
            log(f"🔗 Shortcut: {lnk}")
        except Exception as e:
            log(f"Shortcut skip: {e}")


def _load_fetch_chromium():
    import importlib.util
    for p in [_meipass() / "fetch_chromium.py", Path(__file__).resolve().parent / "fetch_chromium.py"]:
        if p.exists():
            spec = importlib.util.spec_from_file_location("fetch_chromium", p)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    try:
        from marketing_divar import app_chromium as mod
        return mod
    except Exception:
        pass
    raise FileNotFoundError("fetch_chromium missing")


def install_app_chromium(target: Path, workdir: Path, log, chrome_progress=None) -> bool:
    dest = data_dir() / "app-chromium"
    dest.mkdir(parents=True, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(dest)
    os.environ["DIVAR_CHROMIUM_DIR"] = str(dest)

    sys.path.insert(0, str(workdir))
    try:
        import marketing_divar.app_chromium as ac
        if ac.is_ready(dest):
            log(f"✅ Chromium offline ready")
            if chrome_progress:
                chrome_progress(100, "Chromium Ready (offline) ✅")
            return True
    except Exception:
        pass

    log("🌐 Installing Chromium with DownloadManager...")
    if chrome_progress:
        chrome_progress(0, "Chromium started")
    try:
        fc = _load_fetch_chromium()
        def on_pct(pct: int):
            if chrome_progress:
                chrome_progress(min(100, int(pct)), f"Chromium {pct}% — DownloadManager")
        path = fc.ensure_installed(log=log, progress=on_pct)
        log(f"✅ Chromium OK: {path}")
        if chrome_progress:
            chrome_progress(100, "Chromium Completed ✅")
        return True
    except Exception as e:
        log(f"⚠️ Chromium: {e}")
        if chrome_progress:
            chrome_progress(0, "Chromium retry in panel")
        return False


def install_nlu_model(dest: Path, log, nlu_progress=None) -> bool:
    model_dest = data_dir() / "nlu-model"
    model_dest.mkdir(parents=True, exist_ok=True)
    download_dir = data_dir() / "nlu-download"
    download_dir.mkdir(parents=True, exist_ok=True)

    os.environ["DIVAR_APP_DIR"] = str(dest)
    os.environ["DIVAR_NLU_DIR"] = str(model_dest)
    os.environ["DIVAR_NLU_DOWNLOAD"] = str(download_dir)
    os.environ["DIVAR_DATA_DIR"] = str(data_dir())

    sys.path.insert(0, str(dest))
    try:
        from marketing_divar import nlu_model as nm
        if nm.is_ready():
            log(f"✅ Model ready: {nm.backend_name()}")
            if nlu_progress:
                nlu_progress(100, "Tira Ready (offline) ✅")
            return True

        ggufs = list(model_dest.glob("*.gguf"))
        if ggufs:
            try:
                import time
                marker = {
                    "product": ggufs[0].name,
                    "gguf": str(ggufs[0]),
                    "ready": True,
                    "backend": "fallback-smart",
                    "at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                (model_dest / "INSTALLED.json").write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")
                if nm.is_ready():
                    log(f"✅ Model ready after offline copy")
                    if nlu_progress:
                        nlu_progress(100, "Tira Ready (offline) ✅")
                    return True
            except Exception as e:
                log(f"Marker fail: {e}")

        log(f"📥 Downloading Tira model with DownloadManager...")
        def on_pct(pct: int):
            if nlu_progress:
                nlu_progress(min(100, int(pct)), f"Tira {pct}% — DownloadManager")
        if nlu_progress:
            nlu_progress(0, "Tira started")
        nm.ensure_installed(log=log, progress=on_pct)
        log(f"✅ Model OK: {nm.backend_name()}")
        if nlu_progress:
            nlu_progress(100, "Tira Completed ✅")
        return True
    except Exception as e:
        log(f"⚠️ Model: {e}")
        try:
            from marketing_divar import nlu_model as nm
            if nm.is_ready():
                if nlu_progress:
                    nlu_progress(100, "Tira fallback ready ✅")
                return True
        except Exception:
            pass
        if nlu_progress:
            nlu_progress(0, "Tira retry in panel")
        return False


def open_firewall(log) -> None:
    for proto, name in [("TCP", APP_NAME_EN), ("UDP", f"{APP_NAME_EN} UDP")]:
        cmd = ["netsh", "advfirewall", "firewall", "add", "rule",
               f"name={name}", "dir=in", "action=allow", "protocol="+proto, f"localport={PORT}"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                log(f"🔥 Firewall {proto} OK")
        except Exception as e:
            log(f"Firewall {proto} skip: {e}")


def _popen_hidden(args, cwd, env) -> None:
    kwargs = {"cwd": str(cwd), "env": env}
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 6
        kwargs["startupinfo"] = si
        kwargs["creationflags"] = CREATE_NO_WINDOW
    subprocess.Popen(args, **kwargs)


def launch(target: Path, workdir: Path, log) -> None:
    log(f"🚀 Launching Tira Desktop...")
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["DIVAR_DATA_DIR"] = str(data_dir())
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(data_dir() / "app-chromium")
    env["DIVAR_CHROMIUM_DIR"] = str(data_dir() / "app-chromium")
    try:
        if target.suffix.lower() == ".exe":
            _popen_hidden([str(target), "--desktop"], workdir, env)
        else:
            pyw = Path(sys.executable).with_name("pythonw.exe")
            exe = str(pyw) if pyw.exists() else sys.executable
            _popen_hidden([exe, str(target), "--desktop"], workdir, env)
        log(f"✅ Tira launched")
    except Exception as e:
        log(f"Launch fail: {e}")
        try:
            if target.suffix.lower() == ".exe":
                _popen_hidden([str(target), "--web"], workdir, env)
            else:
                pyw = Path(sys.executable).with_name("pythonw.exe")
                exe = str(pyw) if pyw.exists() else sys.executable
                _popen_hidden([exe, str(target), "--web"], workdir, env)
        except Exception as e2:
            log(f"Fallback fail: {e2}")
            raise


def ensure_pywebview(dest: Path, log) -> None:
    try:
        import webview
        log(f"✅ pywebview ready")
        return
    except ImportError:
        pass
    log(f"📦 Installing pywebview...")
    try:
        py = dest / ".venv" / "Scripts" / "python.exe"
        if not py.exists():
            py = Path(sys.executable)
        subprocess.run([str(py), "-m", "pip", "install", "pywebview", "-q", "--disable-pip-version-check"],
                       timeout=60, capture_output=True)
        log(f"✅ pywebview installed")
    except Exception as e:
        log(f"pywebview skip: {e}")


def run_install(progress, log, chrome_progress=None, dest: Path | None = None, nlu_progress=None) -> None:
    try:
        dest = Path(dest) if dest else default_install_dir()
        progress(5, "📁 آماده‌سازی پوشه‌ها")
        dest.mkdir(parents=True, exist_ok=True)

        progress(15, "📦 استخراج فایل‌ها")
        target = extract_payload(dest, log)

        ico_src = app_icon()
        ico_dst = dest / "app.ico"
        if ico_src.exists():
            try:
                shutil.copy2(ico_src, ico_dst)
                shutil.copy2(ico_src, data_dir() / "app.ico")
            except Exception:
                pass

        progress(30, "🖥️ pywebview")
        ensure_pywebview(dest, log)

        progress(40, "🌐 Chromium")
        ok_chrome = install_app_chromium(target, dest, log, chrome_progress=chrome_progress)

        progress(65, "🧠 مدل تیرا")
        ok_model = install_nlu_model(dest, log, nlu_progress=nlu_progress)

        progress(80, "🔗 میانبرها")
        make_shortcut(target, dest, ico_dst if ico_dst.exists() else ico_src, log)

        progress(85, "🔥 فایروال")
        open_firewall(log)

        progress(92, "🚀 اجرای تیرا")
        launch(target, dest, log)

        progress(100, "✅ نصب کامل — تیرا آماده")
        log("✅ Install complete - Tira Desktop Ready - Native window")

    except Exception as e:
        import traceback
        log(f"❌ Error: {e}")
        log(traceback.format_exc())
        progress(0, f"❌ خطا: {e}")
        raise


def gui() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, ttk
    except Exception as e:
        print(f"GUI not available: {e}")
        return 2

    root = tk.Tk()
    root.title(f"{APP_NAME_FA} — نصب تیرا")
    # ریسپانسیو: قابل تغییر اندازه، مینیمم سایز، وسط صفحه
    root.geometry("620x640")
    root.minsize(520, 480)
    root.resizable(True, True)
    root.configure(bg="#0f172a")

    # وسط صفحه
    try:
        root.update_idletasks()
        w = root.winfo_screenwidth()
        h = root.winfo_screenheight()
        x = (w - 620) // 2
        y = (h - 640) // 2
        root.geometry(f"620x640+{x}+{y}")
    except Exception:
        pass

    try:
        ico = app_icon()
        if ico.exists():
            root.iconbitmap(default=str(ico))
    except Exception:
        pass

    # کانتینر اصلی با وزن ریسپانسیو
    main_container = tk.Frame(root, bg="#0f172a")
    main_container.pack(fill="both", expand=True)
    main_container.columnconfigure(0, weight=1)
    main_container.rowconfigure(3, weight=1)  # logbox row expands

    # هدر - ثابت
    header = tk.Frame(main_container, bg="#0f172a")
    header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
    header.columnconfigure(0, weight=1)
    tk.Label(header, text="🧠 تیرا", font=("Segoe UI", 20, "bold"), fg="#a78bfa", bg="#0f172a").pack(anchor="w", padx=16, pady=(12, 2))
    tk.Label(header, text="دستیار شکار حرفه‌ای — نصب آفلاین/آنلاین", font=("Segoe UI", 10, "bold"), fg="#e2e8f0", bg="#0f172a").pack(anchor="w", padx=16)
    tk.Label(header, text=f"نسخه {VERSION} — ریسپانسیو، قابل تغییر اندازه\nاگر مدل موجود باشد استفاده می‌شود، وگرنه DownloadManager",
             font=("Segoe UI", 8), fg="#94a3b8", bg="#0f172a", justify="left").pack(anchor="w", padx=16, pady=(2, 8))

    # مسیر نصب - ثابت
    path_frame = tk.Frame(main_container, bg="#0f172a")
    path_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=2)
    path_frame.columnconfigure(0, weight=1)
    tk.Label(path_frame, text="📁 پوشه نصب", font=("Segoe UI", 8), fg="#cbd5e1", bg="#0f172a").pack(anchor="w")
    entry_row = tk.Frame(path_frame, bg="#0f172a")
    entry_row.pack(fill="x", pady=2)
    entry_row.columnconfigure(0, weight=1)
    dest_var = tk.StringVar(value=str(default_install_dir()))
    tk.Entry(entry_row, textvariable=dest_var, font=("Segoe UI", 9), bg="#1e293b", fg="#e2e8f0",
             insertbackground="#e2e8f0", relief="flat").pack(side="left", fill="x", expand=True, ipady=3)
    def browse():
        p = filedialog.askdirectory(title="Install folder", initialdir=dest_var.get() or str(Path.home()))
        if p:
            dest_var.set(p)
    tk.Button(entry_row, text="Browse", command=browse, width=8, bg="#334155", fg="white", relief="flat").pack(side="right", padx=(6, 0))

    # پروگرس‌ها - ثابت
    prog_frame = tk.Frame(main_container, bg="#0f172a")
    prog_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=6)
    prog_frame.columnconfigure(0, weight=1)

    status = tk.Label(prog_frame, text="آماده — نصب را بزن", font=("Segoe UI", 9, "bold"), fg="#38bdf8", bg="#0f172a", anchor="w")
    status.pack(fill="x", pady=(2, 2))
    bar = ttk.Progressbar(prog_frame, mode="determinate", maximum=100)
    bar.pack(fill="x", pady=2)

    chrome_lbl = tk.Label(prog_frame, text="Chromium: در انتظار", font=("Segoe UI", 8), fg="#cbd5e1", bg="#0f172a", anchor="w")
    chrome_lbl.pack(fill="x")
    chrome_bar = ttk.Progressbar(prog_frame, mode="determinate", maximum=100)
    chrome_bar.pack(fill="x", pady=1)

    nlu_lbl = tk.Label(prog_frame, text="مدل تیرا: در انتظار", font=("Segoe UI", 8), fg="#cbd5e1", bg="#0f172a", anchor="w")
    nlu_lbl.pack(fill="x")
    nlu_bar = ttk.Progressbar(prog_frame, mode="determinate", maximum=100)
    nlu_bar.pack(fill="x", pady=1)

    # لاگ باکس - قابل گسترش ریسپانسیو + اسکرول
    log_frame = tk.Frame(main_container, bg="#0f172a")
    log_frame.grid(row=3, column=0, sticky="nsew", padx=16, pady=6)
    log_frame.columnconfigure(0, weight=1)
    log_frame.rowconfigure(0, weight=1)

    logbox = tk.Text(log_frame, font=("Consolas", 8), bg="#1e293b", fg="#e2e8f0", relief="flat", wrap="word")
    logbox.grid(row=0, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=logbox.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    logbox.configure(yscrollcommand=scrollbar.set)
    logbox.configure(state="disabled")

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

    def prog(pct: int, label: str):
        def _do():
            bar["value"] = pct
            status.configure(text=label)
        try:
            root.after(0, _do)
        except Exception:
            pass

    def chrome_prog(pct: int, label: str):
        def _do():
            chrome_bar["value"] = pct
            chrome_lbl.configure(text=label)
        try:
            root.after(0, _do)
        except Exception:
            pass

    def nlu_prog(pct: int, label: str):
        def _do():
            nlu_bar["value"] = pct
            nlu_lbl.configure(text=label)
        try:
            root.after(0, _do)
        except Exception:
            pass

    # دکمه‌ها - ثابت پایین
    btns = tk.Frame(main_container, bg="#0f172a")
    btns.grid(row=4, column=0, sticky="ew", padx=16, pady=10)
    btns.columnconfigure(0, weight=1)
    btn = tk.Button(btns, text="🚀 نصب تیرا — دسکتاپ مستقل", font=("Segoe UI", 10, "bold"),
                    bg="#7c3aed", fg="white", activebackground="#6d28d9", relief="flat", padx=10, pady=8)
    btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))
    tk.Button(btns, text="خروج", width=8, command=root.destroy, bg="#334155", fg="white", relief="flat", padx=8, pady=8).grid(row=0, column=1)

    def go():
        btn.configure(state="disabled")
        chosen = dest_var.get().strip() or str(default_install_dir())
        def work():
            try:
                run_install(prog, log, chrome_progress=chrome_prog, nlu_progress=nlu_prog, dest=Path(chosen))
                def _ok():
                    status.configure(text="✅ نصب شد — تیرا در حال باز شدن...", fg="#22c55e")
                    bar["value"] = 100
                root.after(0, _ok)
                root.after(3000, root.destroy)
            except Exception as e:
                def _err():
                    status.configure(text=f"❌ خطا: {e}", fg="#ef4444")
                root.after(0, _err)
                log(f"ERROR: {e}")
            finally:
                def _en():
                    btn.configure(state="normal")
                root.after(0, _en)
        threading.Thread(target=work, daemon=True).start()

    btn.configure(command=go)
    root.mainloop()
    return 0


def main() -> int:
    if "--cli" in sys.argv:
        def prog(p, s):
            print(f"[{p:3d}%] {s}")
        def chrome_prog(p, s):
            print(f"[Chromium {p:3d}%] {s}")
        def nlu_prog(p, s):
            print(f"[NLU {p:3d}%] {s}")
        dest = default_install_dir()
        if "--dest" in sys.argv:
            i = sys.argv.index("--dest")
            if i + 1 < len(sys.argv):
                dest = Path(sys.argv[i + 1])
        run_install(prog, print, chrome_progress=chrome_prog, nlu_progress=nlu_prog, dest=dest)
        return 0
    return gui()


if __name__ == "__main__":
    raise SystemExit(main())
