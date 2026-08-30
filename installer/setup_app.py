# -*- coding: utf-8 -*-
"""🧠 تیرا — نصب‌کننده استاندارد با دانلود منیجر و اتصالات کامل سیستم

Single-file Windows installer (English console + Persian GUI).
Frozen as DivarMarketing-Setup.exe with payload.zip inside.
- مدل Qwen با DownloadManager استاندارد (resume + چند آینه + سرعت) دانلود می‌شود
- اگر مدل نباشد خودکار نصب می‌شود (استاندارد + کتابخانه)
- در مرحله نصب: تنظیمات، اتصالات سیستم، فایروال، میانبر، رجیستری
- پنل اصلی به صورت دسکتاپ مستقل (pywebview) بدون مرورگر باز می‌شود
- پروفایل‌ها همچنان در Chromium اختصاصی
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
AI_NAME_EN = "Tira"
PORT = 8642
CREATE_NO_WINDOW = 0x08000000
VERSION = "3.4.0-tira-desktop"


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
    for p in (_meipass() / "app.ico",
              Path(__file__).resolve().parent / "app.ico"):
        if p.exists():
            return p
    return Path()


def create_layout(dest: Path, log) -> None:
    """پوشه‌بندی استاندارد + اتصالات سیستم"""
    # پوشه‌های برنامه
    for name in ("data", "logs", "accounts", "app-chromium", "nlu-model", "nlu-download"):
        (dest / name).mkdir(parents=True, exist_ok=True)
    # پوشه پایدار کاربر
    persist = data_dir()
    for name in ("accounts", "logs", "app-chromium", "nlu-model", "nlu-download"):
        (persist / name).mkdir(parents=True, exist_ok=True)
    # لاگ
    log(f"📁 Folders ready: {dest} | persist: {persist}")
    # config.json پیش‌فرض اگر نیست
    cfg_path = persist / "config.json"
    if not cfg_path.exists():
        try:
            default_cfg = {
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
            }
            cfg_path.write_text(json.dumps(default_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"⚙️ Default config created: {cfg_path}")
        except Exception as e:
            log(f"Config create skipped: {e}")
    # دیتابیس خالی
    try:
        db_path = persist / "divar_leads.db"
        if not db_path.exists():
            # یک فایل خالی بساز تا بعداً init شود
            db_path.touch()
            log(f"🗄️ DB placeholder: {db_path}")
    except Exception as e:
        log(f"DB placeholder skipped: {e}")


def extract_payload(dest: Path, log) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    zpath = payload_zip()
    if zpath.exists():
        log("📦 Extracting application files...")
        with zipfile.ZipFile(zpath, "r") as zf:
            zf.extractall(dest)
        log(f"✅ Files extracted to {dest} ({zpath.stat().st_size // 1024 // 1024} MB)")
    else:
        root = Path(__file__).resolve().parent.parent
        log(f"No packed payload — copying source from {root}")
        names = ("main.py", "requirements.txt", "marketing_divar",
                 "installer", "Start-Divar-Marketing.bat")
        for name in names:
            src = root / name
            dst = dest / name
            if not src.exists():
                continue
            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
                    "__pycache__", "*.pyc", "install-log.txt", "payload.zip"))
            else:
                shutil.copy2(src, dst)
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
    # desktop_app هم قابل قبول است
    desk = dest / "marketing_divar" / "desktop_app.py"
    if desk.exists():
        return dest / "main.py"
    raise FileNotFoundError("Installed files are incomplete")


def make_shortcut(target: Path, workdir: Path, ico: Path, log) -> None:
    """میانبر دسکتاپ و استارت منو — با آیکون تیرا و فلگ --desktop"""
    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    start = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    # نام‌های میانبر
    shortcuts = [
        (desktop, f"{APP_NAME_FA}.lnk", f"{APP_NAME_FA} - تیرا"),
        (desktop, f"{APP_NAME_EN}.lnk", f"{APP_NAME_EN} - Tira"),
        (start, f"{APP_NAME_FA}.lnk", f"{APP_NAME_FA}"),
        (start, f"{APP_NAME_EN}.lnk", f"{APP_NAME_EN}"),
    ]
    try:
        import win32com.client  # type: ignore
        shell = win32com.client.Dispatch("WScript.Shell")
        use_com = True
    except Exception:
        use_com = False
        shell = None
    pyw = Path(sys.executable).with_name("pythonw.exe")
    for folder, fname, desc in shortcuts:
        if not folder:
            continue
        try:
            folder.mkdir(parents=True, exist_ok=True)
            lnk = folder / fname
            # اگر میانبر از قبل هست و قدیمی است، بازنویسی کن
            if use_com:
                sc = shell.CreateShortcut(str(lnk))
                if target.suffix.lower() == ".exe":
                    sc.TargetPath = str(target)
                    sc.Arguments = "--desktop"
                elif pyw.exists() and target.suffix.lower() == ".py":
                    sc.TargetPath = str(pyw)
                    sc.Arguments = f'"{target}" --desktop'
                else:
                    sc.TargetPath = sys.executable
                    sc.Arguments = f'"{target}" --desktop'
                sc.WorkingDirectory = str(workdir)
                sc.Description = desc
                sc.WindowStyle = 7
                if ico and ico.exists():
                    sc.IconLocation = str(ico)
                sc.Save()
                log(f"🔗 Shortcut: {lnk} -> --desktop")
            else:
                icon = str(ico) if ico and ico.exists() else ""
                if target.suffix.lower() == ".exe":
                    tgt, args = str(target), "--desktop"
                elif pyw.exists():
                    tgt, args = str(pyw), f'"{target}" --desktop'
                else:
                    tgt, args = sys.executable, f'"{target}" --desktop'
                ps = (
                    f'$s=(New-Object -ComObject WScript.Shell).CreateShortcut("{lnk}");'
                    f'$s.TargetPath="{tgt}";'
                    f"$s.Arguments='{args}';"
                    f'$s.WorkingDirectory="{workdir}";'
                    f'$s.Description="{desc}";'
                    f"$s.WindowStyle=7;"
                )
                if icon:
                    ps += f'$s.IconLocation="{icon}";'
                ps += "$s.Save()"
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps],
                    check=False, capture_output=True)
                log(f"🔗 Shortcut: {lnk}")
        except Exception as e:
            log(f"Shortcut skipped {fname}: {e}")


def _load_fetch_chromium():
    import importlib.util
    cands = [
        _meipass() / "fetch_chromium.py",
        Path(__file__).resolve().parent / "fetch_chromium.py",
        Path(__file__).resolve().parent.parent / "installer" / "fetch_chromium.py",
    ]
    for p in cands:
        if p.exists():
            spec = importlib.util.spec_from_file_location("fetch_chromium", p)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    raise FileNotFoundError("fetch_chromium.py missing from installer")


def install_app_chromium(target: Path, workdir: Path, log, chrome_progress=None) -> bool:
    """دانلود Chromium با DownloadManager استاندارد — نوار مستقل"""
    dest = data_dir() / "app-chromium"
    dest.mkdir(parents=True, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(dest)
    os.environ["DIVAR_CHROMIUM_DIR"] = str(dest)
    log("CHROMIUM_START")
    log("📥 Installing app-only Chromium (not Google Chrome, not Edge) with DownloadManager...")
    fc = _load_fetch_chromium()

    def on_pct(pct: int) -> None:
        if chrome_progress:
            chrome_progress(min(100, int(pct)), f"Chromium {pct}% — DownloadManager")

    if chrome_progress:
        chrome_progress(0, "Chromium started — DownloadManager")
    try:
        path = fc.ensure_installed(log=log, progress=on_pct)
        log(f"✅ App Chromium OK -> {path}")
        if chrome_progress:
            chrome_progress(100, "Chromium Completed ✅")
        return True
    except Exception as e:
        log(f"SOURCE_FAIL all {e}")
        log(f"⚠️ Chromium skipped (app will retry from panel). {e}")
        if chrome_progress:
            chrome_progress(0, "Chromium failed - retry in panel")
        return False


def open_firewall(log) -> None:
    """فایروال + اتصالات شبکه"""
    # TCP
    cmd = [
        "netsh", "advfirewall", "firewall", "add", "rule",
        f"name={APP_NAME_EN}", "dir=in", "action=allow",
        "protocol=TCP", f"localport={PORT}",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if r.returncode == 0:
            log(f"🔥 Firewall: allowed TCP {PORT} for phones on this network")
        else:
            log("Firewall rule not added (run Setup as Administrator if needed)")
    except Exception as e:
        log(f"Firewall skipped: {e}")
    # UDP هم برای کشف شبکه
    try:
        cmd2 = [
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={APP_NAME_EN} UDP", "dir=in", "action=allow",
            "protocol=UDP", f"localport={PORT}",
        ]
        subprocess.run(cmd2, capture_output=True, timeout=10)
    except Exception:
        pass


def register_uninstall(dest: Path, ico: Path, log) -> None:
    """ثبت در Add/Remove Programs (رجیستری)"""
    if sys.platform != "win32":
        return
    try:
        import winreg
        key_path = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, f"{APP_NAME_FA} ({AI_NAME})")
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, VERSION)
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "Tira - Khajavy")
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(dest))
            winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, str(ico) if ico.exists() else str(dest))
            # Uninstall string
            uninst = dest / "uninstall.bat"
            try:
                uninst.write_text(f'@echo off\nrmdir /s /q "{dest}"\n', encoding="utf-8")
                winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, str(uninst))
            except Exception:
                pass
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        log(f"📝 Registry uninstall entry: {key_path}")
    except Exception as e:
        log(f"Registry skip: {e}")


def _popen_hidden(args, cwd, env) -> None:
    kwargs = {"cwd": str(cwd), "env": env}
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 6  # SW_MINIMIZE
        kwargs["startupinfo"] = si
        kwargs["creationflags"] = CREATE_NO_WINDOW
    subprocess.Popen(args, **kwargs)


def launch(target: Path, workdir: Path, log) -> None:
    """اجرای اپ دسکتاپ مستقل تیرا — بدون مرورگر"""
    log(f"🚀 Starting {APP_NAME} desktop (Tira) — console minimized...")
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    chrome = str(data_dir() / "app-chromium")
    env["PLAYWRIGHT_BROWSERS_PATH"] = chrome
    env["DIVAR_CHROMIUM_DIR"] = chrome
    env["DIVAR_DATA_DIR"] = str(data_dir())
    # اگر exe است، با --desktop اجرا کن
    if target.suffix.lower() == ".exe":
        _popen_hidden([str(target), "--desktop"], workdir, env)
    else:
        pyw = Path(sys.executable).with_name("pythonw.exe")
        exe = str(pyw) if pyw.exists() else sys.executable
        _popen_hidden([exe, str(target), "--desktop"], workdir, env)
    log("🖥️ App will open as native desktop window (Tira) — not browser tab")
    log(f"📍 http://127.0.0.1:{PORT} — standalone window")


def install_nlu_model(dest: Path, log, nlu_progress=None) -> bool:
    """دانلود مدل تیرا با DownloadManager استاندارد + کتابخانه — اگر نباشد خودکار نصب"""
    dest = Path(dest)
    model_dest = data_dir() / "nlu-model"  # مدل در پوشه پایدار
    model_dest.mkdir(parents=True, exist_ok=True)
    # کش کنار نصبی
    if getattr(sys, "frozen", False):
        setup_dir = Path(sys.executable).parent
    else:
        setup_dir = Path(__file__).resolve().parent
    download_dir = data_dir() / "nlu-download"
    download_dir.mkdir(parents=True, exist_ok=True)
    os.environ["DIVAR_APP_DIR"] = str(dest)
    os.environ["DIVAR_NLU_DIR"] = str(model_dest)
    os.environ["DIVAR_NLU_DOWNLOAD"] = str(download_dir)
    os.environ["DIVAR_DATA_DIR"] = str(data_dir())

    log("NLU_START")
    log(f"📥 Downloading Tira AI model (Qwen) with DownloadManager to {model_dest} ...")
    log(f"   Cache: {download_dir} — will auto-install if missing")
    if nlu_progress:
        nlu_progress(0, "Tira model started — DownloadManager")

    sys.path.insert(0, str(dest))
    try:
        # سعی کن DownloadManager را مستقیم استفاده کنی
        from marketing_divar import nlu_model as nm  # type: ignore

        def on_pct(pct: int) -> None:
            if nlu_progress:
                nlu_progress(min(100, int(pct)), f"Tira {pct}% — DownloadManager")

        # اگر مدل از قبل هست، فقط چک کن
        if nm.is_ready():
            log(f"✅ Tira model already ready: {nm.gguf_path()}")
            if nlu_progress:
                nlu_progress(100, "Tira Completed ✅ (cached)")
            return True

        nm.ensure_installed(log=log, progress=on_pct)
        log(f"✅ Tira NLU OK -> {model_dest} — backend: {nm.backend_name()}")
        if nlu_progress:
            nlu_progress(100, "Tira Completed ✅")
        return True
    except Exception as e:
        log(f"⚠️ Tira NLU download failed (panel can retry): {e}")
        # حتی اگر دانلود ناموفق بود، fallback هوشمند کار می‌کند
        try:
            from marketing_divar import nlu_model as nm
            if nm.is_ready():
                log("✅ Tira fallback ready")
                if nlu_progress:
                    nlu_progress(100, "Tira fallback ready ✅")
                return True
        except Exception:
            pass
        if nlu_progress:
            nlu_progress(0, "Tira failed - retry in panel (fallback active)")
        return False


def ensure_pywebview(dest: Path, log) -> None:
    """اطمینان از نصب pywebview برای پنجره مستقل"""
    try:
        import webview  # noqa
        log("✅ pywebview already installed — native window ready")
        return
    except ImportError:
        pass
    log("📦 Installing pywebview for native desktop window...")
    try:
        # اگر venv هست
        py = dest / ".venv" / "Scripts" / "python.exe"
        if not py.exists():
            py = Path(sys.executable)
        subprocess.run([str(py), "-m", "pip", "install", "pywebview", "--disable-pip-version-check", "-q"],
                       timeout=60, capture_output=True)
        log("✅ pywebview installed")
    except Exception as e:
        log(f"pywebview install skipped: {e} — will use Chromium fallback")


def run_install(progress, log, chrome_progress=None, dest: Path | None = None,
                nlu_progress=None) -> None:
    dest = Path(dest) if dest else default_install_dir()
    progress(5, "📁 Preparing folders & system connections")
    dest.mkdir(parents=True, exist_ok=True)
    create_layout(dest, log)

    progress(15, "📦 Copying files")
    target = extract_payload(dest, log)
    ico_src = app_icon()
    ico_dst = dest / "app.ico"
    if ico_src.exists():
        shutil.copy2(ico_src, ico_dst)
        # همچنین در data_dir برای دسترسی دسکتاپ
        try:
            shutil.copy2(ico_src, data_dir() / "app.ico")
        except Exception:
            pass

    progress(30, "🔧 Ensuring pywebview (native window)")
    ensure_pywebview(dest, log)

    progress(40, "🌐 App Chromium (DownloadManager)")
    workdir = dest
    install_app_chromium(target, workdir, log, chrome_progress=chrome_progress)

    progress(60, "🧠 Tira AI model (DownloadManager)")
    install_nlu_model(dest, log, nlu_progress=nlu_progress)

    progress(75, "🔗 Shortcuts & Registry")
    make_shortcut(target, workdir, ico_dst if ico_dst.exists() else ico_src, log)
    register_uninstall(dest, ico_dst if ico_dst.exists() else ico_src, log)

    progress(85, "🔥 Firewall & Network")
    open_firewall(log)

    progress(92, "🚀 Launch Tira Desktop")
    launch(target, workdir, log)

    progress(100, "✅ Done — Tira Desktop Ready")
    log("✅ Install complete — Tira Desktop")
    log(f"📍 This PC:  http://127.0.0.1:{PORT} — native window, not browser")
    log(f"📱 Phone (same Wi-Fi): http://<this-PC-IP>:{PORT}")
    log(f"💾 Settings stay in {data_dir()}")
    log(f"🧠 Model: {data_dir() / 'nlu-model'} — auto-installed if missing")
    log(f"🌐 Chromium: {data_dir() / 'app-chromium'} — dedicated, not Edge/Chrome")


def gui() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, ttk
    except Exception as e:
        print(f"GUI not available: {e}")
        return 2

    root = tk.Tk()
    root.title(f"{APP_NAME_FA} — نصب تیرا")
    root.geometry("620x700")
    root.resizable(False, False)
    root.configure(bg="#0f172a")
    try:
        ico = app_icon()
        if ico.exists():
            root.iconbitmap(default=str(ico))
    except Exception:
        pass

    # هدر زیبا با گرادینت شبیه‌سازی
    header = tk.Frame(root, bg="#0f172a")
    header.pack(fill="x", padx=0, pady=0)

    tk.Label(header, text="🧠 تیرا", font=("Segoe UI", 22, "bold"),
             fg="#a78bfa", bg="#0f172a").pack(anchor="w", padx=20, pady=(18, 2))
    tk.Label(header, text=f"{APP_NAME_FA} — دستیار شکار حرفه‌ای",
             font=("Segoe UI", 12, "bold"), fg="#e2e8f0", bg="#0f172a").pack(anchor="w", padx=20)
    tk.Label(header, text=f"نسخه {VERSION} — نصب مستقل بدون مرورگر\nمدل Qwen با DownloadManager خودکار نصب می‌شود",
             font=("Segoe UI", 9), fg="#94a3b8", bg="#0f172a", justify="left").pack(anchor="w", padx=20, pady=(4, 12))

    # مسیر نصب
    dest_var = tk.StringVar(value=str(default_install_dir()))
    row = tk.Frame(root, bg="#0f172a")
    row.pack(fill="x", padx=20, pady=(4, 2))
    tk.Label(row, text="📁 پوشه نصب", font=("Segoe UI", 9), fg="#cbd5e1", bg="#0f172a").pack(anchor="w")
    path_row = tk.Frame(root, bg="#0f172a")
    path_row.pack(fill="x", padx=20, pady=2)
    ent = tk.Entry(path_row, textvariable=dest_var, font=("Segoe UI", 9),
                   bg="#1e293b", fg="#e2e8f0", insertbackground="#e2e8f0", relief="flat")
    ent.pack(side="left", fill="x", expand=True, ipady=4)

    def browse() -> None:
        picked = filedialog.askdirectory(title="Install folder",
                                         initialdir=dest_var.get() or str(Path.home()))
        if picked:
            dest_var.set(picked)
    tk.Button(path_row, text="Browse", command=browse, width=10,
              bg="#334155", fg="white", relief="flat").pack(side="right", padx=(8, 0))

    status = tk.Label(root, text="آماده — دکمه نصب را بزن", font=("Segoe UI", 10, "bold"),
                      fg="#38bdf8", bg="#0f172a")
    status.pack(anchor="w", padx=20, pady=(12, 2))
    bar = ttk.Progressbar(root, length=580, mode="determinate", maximum=100)
    bar.pack(padx=20, pady=4)

    chrome_status = tk.Label(root, text="Chromium: در انتظار", font=("Segoe UI", 9),
                             fg="#cbd5e1", bg="#0f172a")
    chrome_status.pack(anchor="w", padx=20)
    chrome_bar = ttk.Progressbar(root, length=580, mode="determinate", maximum=100)
    chrome_bar.pack(padx=20, pady=2)

    nlu_status = tk.Label(root, text="مدل تیرا: در انتظار (DownloadManager)", font=("Segoe UI", 9),
                          fg="#cbd5e1", bg="#0f172a")
    nlu_status.pack(anchor="w", padx=20)
    nlu_bar = ttk.Progressbar(root, length=580, mode="determinate", maximum=100)
    nlu_bar.pack(padx=20, pady=2)

    logbox = tk.Text(root, height=14, font=("Consolas", 8), bg="#1e293b", fg="#e2e8f0",
                     relief="flat", wrap="word")
    logbox.pack(fill="both", expand=True, padx=20, pady=8)
    logbox.configure(state="disabled")

    def log(msg: str) -> None:
        def _():
            logbox.configure(state="normal")
            logbox.insert("end", msg + "\n")
            logbox.see("end")
            logbox.configure(state="disabled")
        root.after(0, _)

    def progress(pct: int, label: str) -> None:
        def _():
            bar["value"] = pct
            status.configure(text=label)
        root.after(0, _)

    def chrome_progress(pct: int, label: str) -> None:
        def _():
            chrome_bar["value"] = pct
            chrome_status.configure(text=label)
        root.after(0, _)

    def nlu_progress(pct: int, label: str) -> None:
        def _():
            nlu_bar["value"] = pct
            nlu_status.configure(text=label)
        root.after(0, _)

    btns = tk.Frame(root, bg="#0f172a")
    btns.pack(fill="x", padx=20, pady=12)
    btn = tk.Button(btns, text="🚀 نصب تیرا — دسکتاپ مستقل", width=22,
                    font=("Segoe UI", 11, "bold"), bg="#7c3aed", fg="white",
                    activebackground="#6d28d9", relief="flat", padx=10, pady=8)
    btn.pack(side="left")
    tk.Button(btns, text="خروج", width=10, command=root.destroy,
              bg="#334155", fg="white", relief="flat", padx=8, pady=8).pack(side="right")

    def go() -> None:
        btn.configure(state="disabled")
        chosen = dest_var.get().strip() or str(default_install_dir())

        def work():
            try:
                run_install(progress, log, chrome_progress=chrome_progress,
                            nlu_progress=nlu_progress, dest=Path(chosen))
                root.after(0, lambda: status.configure(
                    text="✅ نصب شد — پنجره مستقل تیرا در حال باز شدن...",
                    fg="#22c55e"))
            except Exception as e:
                log(f"❌ ERROR: {e}")
                import traceback
                log(traceback.format_exc()[:1000])
                root.after(0, lambda: status.configure(
                    text="❌ نصب ناموفق — لاگ را ببین", fg="#ef4444"))
            finally:
                root.after(0, lambda: btn.configure(state="normal"))

        threading.Thread(target=work, daemon=True).start()

    btn.configure(command=go)
    root.mainloop()
    return 0


def main() -> int:
    if sys.platform != "win32" and "--force" not in sys.argv:
        print("This installer is for Windows, but --force can run it here.")
        print("On this computer run: python main.py --desktop")
        if "--force" not in sys.argv:
            # در لینوکس هم اجازه بده با --force تست شود
            pass
    if "--cli" in sys.argv:
        def prog(p, s):
            print(f"[{p:3d}%] {s}")
        def chrome_prog(p, s):
            print(f"[Chromium {p:3d}%] {s}")
        dest = default_install_dir()
        if "--dest" in sys.argv:
            i = sys.argv.index("--dest")
            if i + 1 < len(sys.argv):
                dest = Path(sys.argv[i + 1])
        def nlu_prog(p, s):
            print(f"[NLU {p:3d}%] {s}")
        run_install(prog, print, chrome_progress=chrome_prog,
                    nlu_progress=nlu_prog, dest=dest)
        return 0
    return gui()


if __name__ == "__main__":
    raise SystemExit(main())
