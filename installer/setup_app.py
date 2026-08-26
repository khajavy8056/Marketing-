# -*- coding: utf-8 -*-
"""Single-file Windows installer (English console + GUI).

Frozen as DivarMarketing-Setup.exe with payload.zip next to the script
(inside _MEIPASS). Double-click installs the app — no other files needed.
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


def _meipass() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def install_dir() -> Path:
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


def extract_payload(dest: Path, log) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    zpath = payload_zip()
    if zpath.exists():
        log("Extracting application files...")
        with zipfile.ZipFile(zpath, "r") as zf:
            zf.extractall(dest)
        log("Files extracted to " + str(dest))
    else:
        # Dev / source fallback: copy the repo next to this script
        root = Path(__file__).resolve().parent.parent
        log("No packed payload — copying source from " + str(root))
        for name in ("main.py", "requirements.txt", "marketing_divar"):
            src = root / name
            dst = dest / name
            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(src, dst)
            elif src.exists():
                shutil.copy2(src, dst)
    exe = dest / f"{APP_ID}.exe"
    if exe.exists():
        return exe
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
                else:
                    sc.TargetPath = sys.executable
                    sc.Arguments = f'"{target}"'
                sc.WorkingDirectory = str(workdir)
                sc.Description = APP_NAME
                if ico and ico.exists():
                    sc.IconLocation = str(ico)
                sc.Save()
                log("Shortcut: " + str(lnk))
            else:
                # PowerShell fallback
                icon = str(ico) if ico and ico.exists() else ""
                tgt = str(target)
                args = "" if target.suffix.lower() == ".exe" else f'"{target}"'
                ps = (
                    f'$s=(New-Object -ComObject WScript.Shell).CreateShortcut("{lnk}");'
                    f'$s.TargetPath="{tgt if target.suffix.lower()==".exe" else sys.executable}";'
                    f'$s.Arguments=\'{args}\';'
                    f'$s.WorkingDirectory="{workdir}";'
                    f'$s.Description="{APP_NAME}";'
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


def install_app_chromium(target: Path, workdir: Path, log) -> None:
    """Download Chromium into %LOCALAPPDATA%\\DivarMarketing\\app-chromium.

    Never uses the user's Chrome/Edge. The frozen exe looks in _MEI unless
    PLAYWRIGHT_BROWSERS_PATH is this folder.
    """
    dest = install_dir() / "app-chromium"
    dest.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(dest)
    env["DIVAR_CHROMIUM_DIR"] = str(dest)
    log("Installing app-only Chromium (not your system browser) ...")
    try:
        if target.suffix.lower() == ".exe":
            cmd = [str(target), "--install-chromium"]
        else:
            cmd = [sys.executable, str(target), "--install-chromium"]
        r = subprocess.run(
            cmd, cwd=str(workdir), env=env, capture_output=True,
            text=True, timeout=900)
        out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        for line in out.splitlines()[-12:]:
            if line.strip():
                log("  " + line.strip())
        if r.returncode != 0:
            raise RuntimeError("chromium install exit " + str(r.returncode))
        log("App Chromium OK -> " + str(dest))
    except Exception as e:
        log("ERROR installing Chromium: " + str(e))
        raise


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


def launch(target: Path, workdir: Path, log) -> None:
    log("Starting " + APP_NAME + "...")
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    chrome = str(install_dir() / "app-chromium")
    env["PLAYWRIGHT_BROWSERS_PATH"] = chrome
    env["DIVAR_CHROMIUM_DIR"] = chrome
    if target.suffix.lower() == ".exe":
        subprocess.Popen([str(target)], cwd=str(workdir), env=env)
    else:
        subprocess.Popen([sys.executable, str(target)], cwd=str(workdir), env=env)
    try:
        os.startfile(f"http://127.0.0.1:{PORT}")  # type: ignore[attr-defined]
    except Exception:
        pass


def run_install(progress, log) -> None:
    dest = install_dir()
    progress(8, "Preparing folder")
    dest.mkdir(parents=True, exist_ok=True)
    progress(20, "Copying files")
    target = extract_payload(dest, log)
    ico_src = app_icon()
    ico_dst = dest / "app.ico"
    if ico_src.exists():
        shutil.copy2(ico_src, ico_dst)
    progress(55, "App Chromium")
    workdir = dest if target.suffix.lower() == ".exe" else dest
    install_app_chromium(target, workdir, log)
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
    log("Settings stay in " + str(dest))


def gui() -> int:
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception as e:
        print("GUI not available:", e)
        return 2

    root = tk.Tk()
    root.title(APP_NAME + " Setup")
    root.geometry("560x420")
    root.resizable(False, False)
    try:
        ico = app_icon()
        if ico.exists():
            root.iconbitmap(default=str(ico))
    except Exception:
        pass

    pad = {"padx": 18, "pady": 6}
    tk.Label(root, text=APP_NAME, font=("Segoe UI", 16, "bold")).pack(anchor="w", **pad)
    tk.Label(root, text="Installs the full app. No other files required.",
             font=("Segoe UI", 10), fg="#334").pack(anchor="w", padx=18)
    status = tk.Label(root, text="Ready. Click Install.", font=("Segoe UI", 10))
    status.pack(anchor="w", padx=18, pady=(10, 0))
    bar = ttk.Progressbar(root, length=520, mode="determinate", maximum=100)
    bar.pack(padx=18, pady=10)
    logbox = tk.Text(root, height=12, font=("Consolas", 9), state="disabled")
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

    btns = tk.Frame(root)
    btns.pack(fill="x", padx=18, pady=10)
    btn = tk.Button(btns, text="Install", width=14, font=("Segoe UI", 10, "bold"))
    btn.pack(side="left")
    tk.Button(btns, text="Close", width=12, command=root.destroy).pack(side="right")

    def go() -> None:
        btn.configure(state="disabled")

        def work():
            try:
                run_install(progress, log)
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
        run_install(prog, print)
        return 0
    return gui()


if __name__ == "__main__":
    raise SystemExit(main())
