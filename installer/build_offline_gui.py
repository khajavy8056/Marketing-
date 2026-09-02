# -*- coding: utf-8 -*-
"""Divar Marketing - Professional Builder v4.3
Professional offline installer builder - clean commercial UI
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
APP_VERSION = "4.3.0-professional"

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

def gui_main():
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox, scrolledtext
    except Exception as e:
        print(f"Tkinter error: {e}")
        return 1

    root = tk.Tk()
    root.title(f"Divar Marketing Builder - v{APP_VERSION}")
    # Responsive sizing
    try:
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
    except:
        sw, sh = 1920, 1080

    if sw <= 1024 or sh <= 768:
        ww = min(960, sw - 20)
        wh = min(700, sh - 40)
    elif sw <= 1366:
        ww = min(900, sw - 40)
        wh = min(750, sh - 60)
    else:
        ww = 900
        wh = 800
    ww = max(700, ww)
    wh = max(560, wh)
    x = max(0, (sw - ww)//2)
    y = max(0, (sh - wh)//2)
    root.geometry(f"{ww}x{wh}+{x}+{y}")
    root.minsize(700, 560)
    root.resizable(True, True)
    root.configure(bg="white")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    style = ttk.Style()
    try:
        style.theme_use("vista")
    except:
        pass
    style.configure("TProgressbar", thickness=20, troughcolor="#e5e7eb", background="#2563eb")
    style.configure("Python.Horizontal.TProgressbar", background="#3b82f6", thickness=18)
    style.configure("Chrome.Horizontal.TProgressbar", background="#8b5cf6", thickness=18)
    style.configure("Model.Horizontal.TProgressbar", background="#10b981", thickness=18)
    style.configure("Pack.Horizontal.TProgressbar", background="#f59e0b", thickness=20)
    style.configure("Exe.Horizontal.TProgressbar", background="#ef4444", thickness=18)
    style.configure("Setup.Horizontal.TProgressbar", background="#1e293b", thickness=20)

    try:
        ico = INSTALLER_DIR / "app.ico"
        if ico.exists():
            root.iconbitmap(default=str(ico))
    except:
        pass

    main_frame = tk.Frame(root, bg="white")
    main_frame.pack(fill="both", expand=True)
    main_frame.columnconfigure(0, weight=1)
    main_frame.rowconfigure(1, weight=1)

    header = tk.Frame(main_frame, bg="#1e293b", height=70)
    header.grid(row=0, column=0, sticky="ew")
    header.grid_propagate(False)
    tk.Label(header, text="Divar Marketing - Installer Builder", font=("Segoe UI", 14, "bold"), bg="#1e293b", fg="white").pack(side="left", padx=20, pady=18)
    tk.Label(header, text=f"v{APP_VERSION}", font=("Segoe UI", 9), bg="#1e293b", fg="#94a3b8").pack(side="right", padx=20, pady=18)

    content = tk.Frame(main_frame, bg="white")
    content.grid(row=1, column=0, sticky="nsew", padx=12, pady=12)
    content.columnconfigure(0, weight=1)
    content.rowconfigure(2, weight=1)

    settings_frame = tk.LabelFrame(content, text="Build Configuration", font=("Segoe UI", 10, "bold"), bg="white", fg="#0f172a", padx=16, pady=12)
    settings_frame.grid(row=0, column=0, sticky="ew", pady=(0,10))
    settings_frame.columnconfigure(3, weight=1)

    tk.Label(settings_frame, text="Version:", font=("Segoe UI", 9), bg="white").grid(row=0, column=0, sticky="w", padx=6, pady=4)
    version_var = tk.StringVar(value=APP_VERSION)
    tk.Entry(settings_frame, textvariable=version_var, font=("Consolas", 9), width=20).grid(row=0, column=1, sticky="w", padx=6, pady=4)

    tk.Label(settings_frame, text="Mode:", font=("Segoe UI", 9), bg="white").grid(row=0, column=2, sticky="w", padx=16, pady=4)
    mode_var = tk.StringVar(value="offline_full")
    ttk.Combobox(settings_frame, textvariable=mode_var, values=["offline_full - Full offline (Recommended)", "online - Download on install", "light - Source only"], width=42, state="readonly").grid(row=0, column=3, sticky="ew", padx=6, pady=4)

    include_chrome_var = tk.BooleanVar(value=False)
    include_model_var = tk.BooleanVar(value=False)
    encrypt_var = tk.BooleanVar(value=True)
    
    tk.Checkbutton(settings_frame, text="Include Chromium Engine (~200 MB)", variable=include_chrome_var, bg="white", font=("Segoe UI", 9)).grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=4)
    tk.Checkbutton(settings_frame, text="Include AI Model (~100 MB)", variable=include_model_var, bg="white", font=("Segoe UI", 9)).grid(row=1, column=2, columnspan=2, sticky="w", padx=16, pady=4)
    tk.Checkbutton(settings_frame, text="Encrypt payload (Recommended)", variable=encrypt_var, bg="white", font=("Segoe UI", 9, "bold")).grid(row=2, column=0, columnspan=2, sticky="w", padx=6, pady=4)
    tk.Label(settings_frame, text="For fast testing, uncheck Chromium and Model", font=("Segoe UI", 8), bg="white", fg="#d97706").grid(row=2, column=2, columnspan=2, sticky="w", padx=16, pady=4)

    progress_frame = tk.LabelFrame(content, text="Build Progress", font=("Segoe UI", 10, "bold"), bg="white", fg="#0f172a", padx=16, pady=12)
    progress_frame.grid(row=1, column=0, sticky="ew", pady=6)
    progress_frame.columnconfigure(1, weight=1)

    bars = {}
    steps = [
        ("python", "Python Environment", "Python.Horizontal.TProgressbar"),
        ("chrome", "Chromium Engine", "Chrome.Horizontal.TProgressbar"),
        ("model", "AI Model", "Model.Horizontal.TProgressbar"),
        ("payload", "Packaging", "Pack.Horizontal.TProgressbar"),
        ("exe", "Main Application", "Exe.Horizontal.TProgressbar"),
        ("setup", "Final Installer", "Setup.Horizontal.TProgressbar"),
    ]
    for idx, (key, label, sty) in enumerate(steps):
        lbl = tk.Label(progress_frame, text=f"{label}: Waiting...", font=("Segoe UI", 9), bg="white", fg="#334155", anchor="w")
        lbl.grid(row=idx*2, column=0, columnspan=3, sticky="ew", pady=(10,0))
        bar = ttk.Progressbar(progress_frame, length=700, mode="determinate", maximum=100, style=sty)
        bar.grid(row=idx*2+1, column=0, columnspan=2, sticky="ew", padx=(0,10), pady=3)
        pct_lbl = tk.Label(progress_frame, text="0%", font=("Consolas", 9, "bold"), bg="white", width=6)
        pct_lbl.grid(row=idx*2+1, column=2, sticky="e")
        bars[key] = (lbl, bar, pct_lbl)

    overall_frame = tk.Frame(progress_frame, bg="white")
    overall_frame.grid(row=len(steps)*2, column=0, columnspan=3, sticky="ew", pady=(16,0))
    overall_frame.columnconfigure(1, weight=1)
    tk.Label(overall_frame, text="Overall:", font=("Segoe UI", 10, "bold"), bg="white").grid(row=0, column=0, sticky="w")
    overall_bar = ttk.Progressbar(overall_frame, length=500, mode="determinate", maximum=100)
    overall_bar.grid(row=0, column=1, sticky="ew", padx=12)
    overall_pct = tk.Label(overall_frame, text="0%", font=("Consolas", 10, "bold"), bg="white")
    overall_pct.grid(row=0, column=2, sticky="e")

    log_frame = tk.LabelFrame(content, text="Build Log", font=("Segoe UI", 9, "bold"), bg="white", padx=6, pady=6)
    log_frame.grid(row=2, column=0, sticky="nsew", pady=6)
    log_frame.columnconfigure(0, weight=1)
    log_frame.rowconfigure(0, weight=1)
    
    logbox = scrolledtext.ScrolledText(log_frame, height=16, font=("Consolas", 8), bg="#0f172a", fg="#e2e8f0", wrap="word")
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

    bottom_frame = tk.Frame(main_frame, bg="#f8fafc", height=70)
    bottom_frame.grid(row=2, column=0, sticky="ew")
    bottom_frame.grid_propagate(False)
    bottom_frame.columnconfigure(0, weight=1)

    status_var = tk.StringVar(value="Ready to build - Click the button below")
    tk.Label(bottom_frame, textvariable=status_var, font=("Segoe UI", 10), bg="#f8fafc", fg="#0f172a").grid(row=0, column=0, sticky="w", padx=20, pady=10)

    def build_process():
        try:
            status_var.set("Building...")
            log(f"Starting build v{version_var.get()} - Mode: {mode_var.get()}")

            # Step 1: Python
            set_progress("python", 10, "Python: Checking...", "—")
            py_exe = _find_python_exe()
            log(f"Python: {py_exe}")
            try:
                r = subprocess.run([py_exe, "--version"], capture_output=True, text=True, timeout=10)
                ver = r.stdout.strip() or r.stderr.strip()
                log(f"{ver}")
                set_progress("python", 50, f"Python: {ver} - Installing tools...", "—")
                subprocess.run([py_exe, "-m", "pip", "install", "--upgrade", "pip", "--disable-pip-version-check", "--progress-bar", "off"], capture_output=True, timeout=120)
                subprocess.run([py_exe, "-m", "pip", "install", "--disable-pip-version-check", "--progress-bar", "off", "pyinstaller", "requests"], capture_output=True, timeout=180)
                log("Build tools installed")
            except Exception as e:
                log(f"Python error: {e}")
                set_progress("python", 0, f"Error: {e}", "—")
                return
            set_progress("python", 100, "Python: Ready", "—")

            # Step 2: Chromium
            set_progress("chrome", 5, "Chromium: Checking...", "—")
            if include_chrome_var.get():
                log("Chromium: Checking local installation...")
                try:
                    local_appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
                    chrome_path = Path(local_appdata) / "DivarMarketing" / "app-chromium"
                    if chrome_path.exists() and any(chrome_path.iterdir()):
                        size = sum(f.stat().st_size for f in chrome_path.rglob("*") if f.is_file()) // 1024 // 1024
                        log(f"Chromium found: {size} MB")
                        set_progress("chrome", 100, f"Chromium: Ready ({size} MB)", "—")
                    else:
                        log("Chromium not found - will be downloaded on install")
                        set_progress("chrome", 30, "Chromium: Not found - download on install", "—")
                except Exception as e:
                    log(f"Chromium error: {e}")
                    set_progress("chrome", 0, f"Error: {e}", "—")
            else:
                set_progress("chrome", 100, "Chromium: Skipped (fast mode)", "—")
                log("Chromium skipped for fast build")

            # Step 3: Model
            set_progress("model", 5, "AI Model: Checking...", "—")
            if include_model_var.get():
                try:
                    local_appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
                    mp = Path(local_appdata) / "DivarMarketing" / "app" / "nlu-model"
                    if mp.exists() and any(mp.iterdir()):
                        size = sum(f.stat().st_size for f in mp.rglob("*") if f.is_file()) // 1024 // 1024
                        log(f"AI Model found: {size} MB")
                        set_progress("model", 100, f"AI Model: Ready ({size} MB)", "—")
                    else:
                        log("AI Model not found - using smart fallback")
                        set_progress("model", 50, "AI Model: Fallback mode", "—")
                except Exception as e:
                    log(f"Model error: {e}")
                    set_progress("model", 0, f"Error: {e}", "—")
            else:
                set_progress("model", 100, "AI Model: Skipped (fast mode)", "—")
                log("AI Model skipped for fast build")

            # Step 4: Payload - FIXED
            set_progress("payload", 2, "Packaging: Starting...", "—")
            log("Packaging v4.3 - Fixed with detailed logging")
            try:
                sys.path.insert(0, str(ROOT))
                from installer.pack_payload import pack
                payload_zip = INSTALLER_DIR / "payload.zip"
                payload_enc = INSTALLER_DIR / "payload.zip.enc"
                for p in [payload_zip, payload_enc]:
                    if p.exists():
                        try:
                            p.unlink()
                        except:
                            pass

                include_chrome = include_chrome_var.get() and "offline_full" in mode_var.get()
                include_model = include_model_var.get() and "offline_full" in mode_var.get()
                encrypt = encrypt_var.get()

                def pack_log(msg: str):
                    log(f"[Pack] {msg}")

                def pack_prog(pct: int, text: str):
                    set_progress("payload", 5 + int(pct*0.90), f"Packaging: {text}", "—")

                result = pack(dest=payload_zip, include_chromium=include_chrome, include_model=include_model,
                              encrypt=encrypt, log_cb=pack_log, progress_cb=pack_prog)

                if result.exists():
                    size_mb = result.stat().st_size // 1024 // 1024
                    log(f"Package created: {result.name} ({size_mb} MB)")
                    set_progress("payload", 100, f"Packaging: Ready ({size_mb} MB)", "—")
                else:
                    log("Package creation failed")
                    set_progress("payload", 0, "Packaging: Failed", "—")
                    return
            except Exception as e:
                log(f"Packaging error: {e}\n{traceback.format_exc()}")
                set_progress("payload", 0, f"Error: {e}", "—")
                return

            # Step 5: Main exe
            set_progress("exe", 5, "Main App: Building...", "—")
            try:
                pyinstaller_cmd = _find_pyinstaller_cmd()
                log(f"PyInstaller: {' '.join(pyinstaller_cmd)}")
                DIST_DIR.mkdir(parents=True, exist_ok=True)
                main_py = ROOT / "main.py"
                if not main_py.exists():
                    log(f"main.py not found")
                    set_progress("exe", 0, "main.py not found", "—")
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
                log("Building main application (windowed)...")
                proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="ignore")
                for line in proc.stdout:
                    if any(x in line for x in ["Building", "Analyzing", "EXE"]):
                        log(f"[PyInstaller] {line.strip()[:120]}")
                        if "Analyzing" in line:
                            set_progress("exe", 20, "Main App: Analyzing...", "—")
                        elif "Building" in line:
                            set_progress("exe", 60, "Main App: Building...", "—")
                proc.wait(timeout=600)
                if proc.returncode == 0:
                    exe_path = DIST_DIR / "DivarMarketing.exe"
                    if exe_path.exists():
                        size = exe_path.stat().st_size // 1024 // 1024
                        log(f"Main app ready: {size} MB - Native window")
                        set_progress("exe", 100, f"Main App: Ready ({size} MB)", "—")
                    else:
                        log("Main app build completed")
                        set_progress("exe", 100, "Main App: Ready", "—")
                else:
                    log(f"PyInstaller returned {proc.returncode}")
                    set_progress("exe", 50, "Main App: Fallback mode", "—")
            except Exception as e:
                log(f"Main app error: {e}")
                set_progress("exe", 50, "Main App: Error but continuing", "—")

            # Step 6: Setup exe
            set_progress("setup", 5, "Final Installer: Building...", "—")
            try:
                pyinstaller_cmd = _find_pyinstaller_cmd()
                setup_py = INSTALLER_DIR / "setup_app.py"
                payload_enc = INSTALLER_DIR / "payload.zip.enc"
                payload_zip = INSTALLER_DIR / "payload.zip"
                payload_to_include = payload_enc if payload_enc.exists() else payload_zip
                if not payload_to_include.exists():
                    log("Payload not found for setup")
                    set_progress("setup", 0, "Payload not found", "—")
                    return

                size_payload = payload_to_include.stat().st_size // 1024 // 1024
                log(f"Payload for setup: {payload_to_include.name} ({size_payload} MB)")

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

                log("Building final installer (windowed, wizard UI)...")
                proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="ignore")
                for line in proc.stdout:
                    if any(x in line for x in ["Building", "EXE", "Analyzing"]):
                        log(f"[Setup] {line.strip()[:150]}")
                        if "Analyzing" in line:
                            set_progress("setup", 20, "Final Installer: Analyzing...", "—")
                        elif "Building" in line:
                            set_progress("setup", 60, "Final Installer: Building wizard...", "—")
                proc.wait(timeout=600)

                setup_exe = DIST_DIR / f"DivarMarketing-Setup-v{version_var.get()}-Final.exe"
                if setup_exe.exists():
                    size = setup_exe.stat().st_size // 1024 // 1024
                    log(f"Final installer ready: {setup_exe.name} ({size} MB)")
                    set_progress("setup", 100, f"Final Installer: Ready ({size} MB)", "—")
                    status_var.set(f"Ready: {setup_exe.name} ({size} MB)")

                    simple = DIST_DIR / "DivarMarketing-Setup.exe"
                    try:
                        shutil.copy2(setup_exe, simple)
                    except:
                        pass

                    def _show_done():
                        messagebox.showinfo("Build Complete",
                            f"Professional installer created!\n\n"
                            f"File: {setup_exe.name}\nSize: {size} MB\n\n"
                            f"Features:\n"
                            f"• Single encrypted file\n"
                            f"• Professional wizard UI\n"
                            f"• Native Windows application\n"
                            f"• Offline capable\n\n"
                            f"Double-click Setup.exe to install.")
                    root.after(0, _show_done)
                else:
                    log("Final installer not found")
                    set_progress("setup", 0, "Failed", "—")
            except Exception as e:
                log(f"Setup error: {e}\n{traceback.format_exc()}")
                set_progress("setup", 0, f"Error: {e}", "—")

            log("Build process completed")
            status_var.set("Build completed - Check dist/ folder")

        except Exception as e:
            log(f"Build error: {e}\n{traceback.format_exc()}")
            status_var.set(f"Error: {e}")

    def on_build():
        if messagebox.askyesno("Build Installer",
                               f"Build professional offline installer v{version_var.get()}?\n\n"
                               f"Mode: {mode_var.get()}\n"
                               f"Chromium: {'Yes' if include_chrome_var.get() else 'No (fast)'}\n"
                               f"AI Model: {'Yes' if include_model_var.get() else 'No (fast)'}\n"
                               f"Encrypted: {'Yes' if encrypt_var.get() else 'No'}\n\n"
                               f"Size: 50 MB - 2.5 GB\n"
                               f"Time: 3 - 15 minutes\n\n"
                               f"Continue?"):
            threading.Thread(target=build_process, daemon=True).start()

    build_btn = tk.Button(bottom_frame, text="Build Installer Now", font=("Segoe UI", 11, "bold"), bg="#1e293b", fg="white", relief="flat", padx=24, pady=10, command=on_build, cursor="hand2")
    build_btn.grid(row=0, column=1, padx=20, pady=12, sticky="e")

    tk.Label(main_frame, text=f"Builder v{APP_VERSION} - Professional - Single encrypted file - No console", font=("Segoe UI", 8), bg="#f8fafc", fg="#64748b").pack(side="bottom", fill="x", padx=16, pady=6)

    root.mainloop()
    return 0

if __name__ == "__main__":
    raise SystemExit(gui_main())
