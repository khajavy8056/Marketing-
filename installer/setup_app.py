# -*- coding: utf-8 -*-
"""Single-file Windows installer (English console + GUI).

Frozen as DivarMarketing-Setup.exe with payload.zip inside.
Double-click installs the app into a folder you pick — one file, like Office.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import zipfile
from pathlib import Path

APP_ID = "DivarMarketing"
APP_NAME = "Divar Marketing"
PORT = 8642
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
    for p in (_meipass() / "app.ico",
              Path(__file__).resolve().parent / "app.ico"):
        if p.exists():
            return p
    return Path()


def create_layout(dest: Path, log) -> None:
    for name in ("data", "logs", "accounts", "app-chromium"):
        (dest / name).mkdir(parents=True, exist_ok=True)
    persist = data_dir()
    for name in ("accounts", "logs", "app-chromium"):
        (persist / name).mkdir(parents=True, exist_ok=True)
    log("Folders ready: " + str(dest))


def extract_payload(dest: Path, log) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    zpath = payload_zip()
    if zpath.exists():
        log("Extracting application files...")
        with zipfile.ZipFile(zpath, "r") as zf:
            zf.extractall(dest)
        log("Files extracted to " + str(dest))
    else:
        root = Path(__file__).resolve().parent.parent
        log("No packed payload — copying source from " + str(root))
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
    raise FileNotFoundError("Installed files are incomplete")


def make_shortcut(target: Path, workdir: Path, ico: Path, log) -> None:
    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    start = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    try:
        import win32com.client  # type: ignore
        shell = win32com.client.Dispatch("WScript.Shell")
        use_com = True
    except Exception:
        use_com = False
        shell = None
    pyw = Path(sys.executable).with_name("pythonw.exe")
    for folder, fname in ((desktop, f"{APP_NAME}.lnk"),
                          (start, f"{APP_NAME}.lnk")):
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
                elif pyw.exists() and target.suffix.lower() == ".py":
                    sc.TargetPath = str(pyw)
                    sc.Arguments = f'"{target}"'
                else:
                    sc.TargetPath = sys.executable
                    sc.Arguments = f'"{target}"'
                sc.WorkingDirectory = str(workdir)
                sc.Description = APP_NAME
                sc.WindowStyle = 7
                if ico and ico.exists():
                    sc.IconLocation = str(ico)
                sc.Save()
                log("Shortcut: " + str(lnk))
            else:
                icon = str(ico) if ico and ico.exists() else ""
                if target.suffix.lower() == ".exe":
                    tgt, args = str(target), ""
                elif pyw.exists():
                    tgt, args = str(pyw), f'"{target}"'
                else:
                    tgt, args = sys.executable, f'"{target}"'
                ps = (
                    f'$s=(New-Object -ComObject WScript.Shell).CreateShortcut("{lnk}");'
                    f'$s.TargetPath="{tgt}";'
                    f"$s.Arguments='{args}';"
                    f'$s.WorkingDirectory="{workdir}";'
                    f'$s.Description="{APP_NAME}";'
                    f"$s.WindowStyle=7;"
                )
                if icon:
                    ps += f'$s.IconLocation="{icon}";'
                ps += "$s.Save()"
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps],
                    check=False, capture_output=True)
                log("Shortcut: " + str(lnk))
        except Exception as e:
            log("Shortcut skipped: " + str(e))


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
    """Download ungoogled-chromium into the app folder.

    Independent Chromium bar (started / percent / bytes / speed / Completed).
    Dead hosts are skipped quickly. Does not spawn Playwright (that hangs).
    Returns True if chrome.exe is ready.
    """
    dest = data_dir() / "app-chromium"
    dest.mkdir(parents=True, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(dest)
    os.environ["DIVAR_CHROMIUM_DIR"] = str(dest)
    log("CHROMIUM_START")
    log("Installing app-only Chromium (not Google Chrome, not Edge) ...")
    fc = _load_fetch_chromium()

    def on_pct(pct: int) -> None:
        if chrome_progress:
            chrome_progress(min(100, int(pct)), "Chromium %d%%" % pct)

    if chrome_progress:
        chrome_progress(0, "Chromium started")
    try:
        path = fc.ensure_installed(log=log, progress=on_pct)
        log("App Chromium OK -> " + str(path))
        if chrome_progress:
            chrome_progress(100, "Chromium Completed")
        return True
    except Exception as e:
        log("SOURCE_FAIL all " + str(e))
        log("Chromium skipped (app will retry from the panel). " + str(e))
        if chrome_progress:
            chrome_progress(0, "Chromium failed - retry in panel")
        return False


def open_firewall(log) -> None:
    cmd = [
        "netsh", "advfirewall", "firewall", "add", "rule",
        f"name={APP_NAME}", "dir=in", "action=allow",
        "protocol=TCP", f"localport={PORT}",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if r.returncode == 0:
            log(f"Firewall: allowed TCP {PORT} for phones on this network")
        else:
            log("Firewall rule not added (run Setup as Administrator if needed)")
    except Exception as e:
        log("Firewall skipped: " + str(e))


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
    log("Starting " + APP_NAME + " (console minimized)...")
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
    log("App will open the panel in dedicated Chromium (not Edge).")


def run_install(progress, log, chrome_progress=None, dest: Path | None = None) -> None:
    dest = Path(dest) if dest else default_install_dir()
    progress(8, "Preparing folder")
    dest.mkdir(parents=True, exist_ok=True)
    progress(20, "Copying files")
    target = extract_payload(dest, log)
    ico_src = app_icon()
    ico_dst = dest / "app.ico"
    if ico_src.exists():
        shutil.copy2(ico_src, ico_dst)
    progress(55, "App files ready")
    workdir = dest
    install_app_chromium(target, workdir, log, chrome_progress=chrome_progress)
    progress(72, "Shortcuts")
    make_shortcut(target, workdir, ico_dst if ico_dst.exists() else ico_src, log)
    progress(80, "Network")
    open_firewall(log)
    progress(92, "Launch")
    launch(target, workdir, log)
    progress(100, "Done")
    log("Install complete.")
    log(f"This PC:  http://127.0.0.1:{PORT}")
    log(f"Phone (same Wi-Fi): http://<this-PC-IP>:{PORT}")
    log("Settings stay in " + str(data_dir()))


def gui() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, ttk
    except Exception as e:
        print("GUI not available:", e)
        return 2

    root = tk.Tk()
    root.title(APP_NAME + " Setup")
    root.geometry("580x560")
    root.resizable(False, False)
    try:
        ico = app_icon()
        if ico.exists():
            root.iconbitmap(default=str(ico))
    except Exception:
        pass

    pad = {"padx": 18, "pady": 6}
    tk.Label(root, text=APP_NAME, font=("Segoe UI", 16, "bold")).pack(anchor="w", **pad)
    tk.Label(root, text="One installer. Pick a folder. Progress bar fills. App starts hidden.",
             font=("Segoe UI", 10), fg="#334").pack(anchor="w", padx=18)

    dest_var = tk.StringVar(value=str(default_install_dir()))
    row = tk.Frame(root)
    row.pack(fill="x", padx=18, pady=(10, 4))
    tk.Label(row, text="Install folder", font=("Segoe UI", 9)).pack(anchor="w")
    path_row = tk.Frame(root)
    path_row.pack(fill="x", padx=18)
    ent = tk.Entry(path_row, textvariable=dest_var, font=("Segoe UI", 9))
    ent.pack(side="left", fill="x", expand=True)
    def browse() -> None:
        picked = filedialog.askdirectory(title="Install folder",
                                         initialdir=dest_var.get() or str(Path.home()))
        if picked:
            dest_var.set(picked)
    tk.Button(path_row, text="Browse", command=browse, width=10).pack(side="right", padx=(8, 0))

    status = tk.Label(root, text="Ready. Click Install.", font=("Segoe UI", 10))
    status.pack(anchor="w", padx=18, pady=(10, 0))
    bar = ttk.Progressbar(root, length=540, mode="determinate", maximum=100)
    bar.pack(padx=18, pady=(8, 4))
    chrome_status = tk.Label(root, text="Chromium: waiting", font=("Segoe UI", 9),
                             fg="#334")
    chrome_status.pack(anchor="w", padx=18)
    chrome_bar = ttk.Progressbar(root, length=540, mode="determinate", maximum=100)
    chrome_bar.pack(padx=18, pady=(4, 8))
    logbox = tk.Text(root, height=11, font=("Consolas", 9), state="disabled")
    logbox.pack(fill="both", expand=True, padx=18, pady=6)

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

    btns = tk.Frame(root)
    btns.pack(fill="x", padx=18, pady=10)
    btn = tk.Button(btns, text="Install", width=14, font=("Segoe UI", 10, "bold"))
    btn.pack(side="left")
    tk.Button(btns, text="Close", width=12, command=root.destroy).pack(side="right")

    def go() -> None:
        btn.configure(state="disabled")
        chosen = dest_var.get().strip() or str(default_install_dir())

        def work():
            try:
                run_install(progress, log, chrome_progress=chrome_progress,
                            dest=Path(chosen))
                root.after(0, lambda: status.configure(
                    text="Installed. App is starting — browser: http://127.0.0.1:8642",
                    fg="#166534"))
            except Exception as e:
                log("ERROR: " + str(e))
                root.after(0, lambda: status.configure(
                    text="Install failed. See log.", fg="#991b1b"))
            finally:
                root.after(0, lambda: btn.configure(state="normal"))

        threading.Thread(target=work, daemon=True).start()

    btn.configure(command=go)
    root.mainloop()
    return 0


def main() -> int:
    if sys.platform != "win32" and "--force" not in sys.argv:
        print("This installer is for Windows.")
        print("On this computer run: python main.py")
        return 0
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
        run_install(prog, print, chrome_progress=chrome_prog, dest=dest)
        return 0
    return gui()


if __name__ == "__main__":
    raise SystemExit(main())
