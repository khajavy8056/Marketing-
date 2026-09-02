# -*- coding: utf-8 -*-
"""Divar Marketing - Professional Commercial Installer v4.3.2 Fixed Crash Responsive
Commercial-grade Windows installer - responsive, clean, professional, no crash
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
import traceback
from pathlib import Path
from typing import Callable, Optional

APP_ID = "DivarMarketing"
APP_NAME = "Divar Marketing"
APP_NAME_FA = "مارکتینگ دیوار"
APP_VERSION = "4.3.2-fixed-crash"
PORT = 8642
CREATE_NO_WINDOW = 0x08000000
ENCRYPTION_KEY = b"DivarMarketing-2024-Secure-Key-Tira-v4.3-Professional"

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
    ]

def app_icon() -> Path:
    for p in (_meipass() / "app.ico", Path(__file__).resolve().parent / "app.ico"):
        if p.exists():
            return p
    return Path()

def decrypt_data(data: bytes, key: bytes = ENCRYPTION_KEY) -> bytes:
    try:
        key_hash = hashlib.sha256(key).digest()
        if len(data) > 12:
            try:
                total_size = int.from_bytes(data[:8], 'big')
                chunk_len = int.from_bytes(data[8:12], 'big')
                if 0 < total_size < 10*1024*1024*1024 and 0 < chunk_len < 50*1024*1024 and len(data) > 12 + chunk_len:
                    out = bytearray()
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
                        compressed = bytes(b ^ key_hash[i % len(key_hash)] for i, b in enumerate(xored))
                        try:
                            chunk = zlib.decompress(compressed)
                        except:
                            chunk = compressed
                        out.extend(chunk)
                        if len(out) >= total_size:
                            break
                    return bytes(out)
            except:
                pass
        xored = bytes(b ^ key_hash[i % len(key_hash)] for i, b in enumerate(data))
        try:
            return zlib.decompress(xored)
        except:
            return xored
    except:
        return data

def decrypt_file_chunked(src_path: Path, dest_path: Path, key: bytes = ENCRYPTION_KEY) -> Path:
    try:
        key_hash = hashlib.sha256(key).digest()
        with open(src_path, 'rb') as fin:
            header = fin.read(12)
            if len(header) < 12:
                fin.seek(0)
                data = fin.read()
                dec = decrypt_data(data, key)
                dest_path.write_bytes(dec)
                return dest_path
            total_size = int.from_bytes(header[:8], 'big')
            first_chunk_len = int.from_bytes(header[8:12], 'big')
            if not (0 < total_size < 10*1024*1024*1024 and 0 < first_chunk_len < 50*1024*1024):
                fin.seek(0)
                data = fin.read()
                dec = decrypt_data(data, key)
                dest_path.write_bytes(dec)
                return dest_path
            fin.seek(0)
            fin.read(8)
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
    except Exception:
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
            except:
                pass
    except:
        pass
    return info

def create_layout(dest: Path, log: Callable[[str], None]) -> None:
    for name in ("data", "logs", "accounts", "app-chromium", "nlu-model"):
        (dest / name).mkdir(parents=True, exist_ok=True)
    persist = data_dir()
    for name in ("accounts", "logs", "app-chromium", "nlu-model", "data"):
        (persist / name).mkdir(parents=True, exist_ok=True)

def extract_payload(dest: Path, log: Callable[[str], None], progress_cb: Optional[Callable[[int, str], None]] = None, preserve_mode: str = "keep") -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    zpath = find_payload()
    prev = has_previous_data()
    if prev["exists"] and preserve_mode != "delete_all":
        if preserve_mode == "keep_accounts":
            try:
                for db_path in [data_dir() / "app" / "data" / "divar_leads.db", data_dir() / "data" / "divar_leads.db"]:
                    if db_path.exists():
                        db_path.unlink()
            except Exception as e:
                log(f"Database cleanup: {e}")
    elif prev["exists"] and preserve_mode == "delete_all":
        try:
            for p in [data_dir() / "data", data_dir() / "logs"]:
                if p.exists():
                    shutil.rmtree(p, ignore_errors=True)
            acc = data_dir() / "accounts"
            if acc.exists():
                shutil.rmtree(acc, ignore_errors=True)
        except Exception as e:
            log(f"Cleanup: {e}")
    if not zpath:
        root = Path(__file__).resolve().parent.parent
        names = ("main.py", "requirements.txt", "marketing_divar", "installer")
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
                progress_cb(int((idx+1)/len(names)*70), f"Copying {name}...")
    else:
        if progress_cb:
            progress_cb(5, "Decrypting installer...")
        try:
            with open(zpath, 'rb') as f:
                head = f.read(2)
            is_encrypted = zpath.suffix == ".enc" or head != b"PK"
        except:
            is_encrypted = zpath.suffix == ".enc"
        tmp_zip = dest.parent / "_payload_tmp.zip"
        if is_encrypted:
            if progress_cb:
                progress_cb(10, "Decrypting...")
            try:
                decrypt_file_chunked(zpath, tmp_zip)
            except Exception:
                try:
                    data = zpath.read_bytes()
                    data = decrypt_data(data)
                    tmp_zip.write_bytes(data)
                except Exception as e2:
                    raise
        else:
            shutil.copy2(zpath, tmp_zip)
        if progress_cb:
            progress_cb(20, "Extracting files...")
        with zipfile.ZipFile(tmp_zip, "r") as zf:
            members = zf.infolist()
            total = len(members)
            for idx, member in enumerate(members):
                zf.extract(member, dest)
                if progress_cb and idx % 30 == 0:
                    pct = 20 + int((idx/total)*60)
                    progress_cb(pct, f"Extracting {idx}/{total}...")
        tmp_zip.unlink(missing_ok=True)
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
    except:
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
                sc.Description = f"{APP_NAME} {APP_VERSION}"
                sc.WindowStyle = 1
                if ico and ico.exists():
                    sc.IconLocation = str(ico)
                sc.Save()
            else:
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
        except Exception as e:
            log(f"Shortcut: {e}")

def open_firewall(log: Callable[[str], None]) -> None:
    cmd = ["netsh", "advfirewall", "firewall", "add", "rule", f"name={APP_NAME}", "dir=in", "action=allow", "protocol=TCP", f"localport={PORT}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            log("Firewall: Run as Administrator for network access")
    except Exception as e:
        log(f"Firewall: {e}")

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

def gui_wizard() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, ttk, messagebox
    except Exception as e:
        print(f"GUI error: {e}")
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f"GUI error: {e}", f"{APP_NAME} Setup", 0x10)
        except:
            pass
        return 2

    try:
        root = tk.Tk()
    except Exception as e:
        print(f"Failed to create Tk root: {e}")
        traceback.print_exc()
        return 2

    try:
        root.title(f"{APP_NAME} Setup")
        try:
            sw = root.winfo_screenwidth()
            sh = root.winfo_screenheight()
        except:
            sw, sh = 1920, 1080

        if sw <= 1024 or sh <= 768:
            ww = min(900, sw - 40)
            wh = min(650, sh - 60)
        elif sw <= 1366 or sh <= 768:
            ww = min(800, sw - 80)
            wh = min(620, sh - 80)
        elif sw <= 1600:
            ww = 780
            wh = 620
        else:
            ww = 800
            wh = 650

        ww = max(640, ww)
        wh = max(500, wh)
        x = max(0, (sw - ww) // 2)
        y = max(0, (sh - wh) // 2)

        root.geometry(f"{ww}x{wh}+{x}+{y}")
        root.minsize(640, 500)
        root.resizable(True, True)
        root.configure(bg="white")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        try:
            ico = app_icon()
            if ico.exists():
                root.iconbitmap(default=str(ico))
        except:
            pass

        style = ttk.Style()
        try:
            style.theme_use("vista")
        except:
            pass
        style.configure("TProgressbar", thickness=20, troughcolor="#e5e7eb", background="#2563eb")

        current_step = [0]
        install_dir_var = tk.StringVar(value=str(default_install_dir()))
        agree_var = tk.BooleanVar(value=False)
        comp_chrome_var = tk.BooleanVar(value=True)
        comp_model_var = tk.BooleanVar(value=True)
        comp_shortcut_var = tk.BooleanVar(value=True)
        preserve_var = tk.StringVar(value="keep")

        main_frame = tk.Frame(root, bg="white")
        main_frame.grid(row=0, column=0, sticky="nsew")
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)

        header = tk.Frame(main_frame, bg="#1e293b", height=56)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.columnconfigure(1, weight=1)
        tk.Label(header, text=APP_NAME_FA, font=("Segoe UI", 13, "bold"), bg="#1e293b", fg="white").grid(row=0, column=0, sticky="w", padx=16, pady=(8,0))
        tk.Label(header, text=APP_NAME, font=("Segoe UI", 8), bg="#1e293b", fg="#94a3b8").grid(row=1, column=0, sticky="w", padx=16, pady=(0,6))
        tk.Label(header, text=f"v{APP_VERSION}", font=("Segoe UI", 8), bg="#1e293b", fg="#94a3b8").grid(row=0, column=2, rowspan=2, sticky="e", padx=16)

        steps_bar = tk.Frame(main_frame, bg="#f8fafc")
        steps_bar.grid(row=1, column=0, sticky="ew")
        steps_bar.columnconfigure(0, weight=1)
        steps_inner = tk.Frame(steps_bar, bg="#f8fafc")
        steps_inner.pack(fill="x", padx=8, pady=5)
        step_labels = []
        step_names = ["Welcome", "License", "Data", "Location", "Components", "Install", "Finish"]
        for i, name in enumerate(step_names):
            lbl = tk.Label(steps_inner, text=f"{i+1}. {name}", font=("Segoe UI", 7), bg="#f8fafc", fg="#2563eb" if i==0 else "#64748b")
            lbl.pack(side="left", padx=6, pady=2)
            step_labels.append(lbl)
            if i < len(step_names)-1:
                tk.Label(steps_inner, text=">", font=("Segoe UI", 7), bg="#f8fafc", fg="#cbd5e1").pack(side="left")

        content_frame = tk.Frame(main_frame, bg="white")
        content_frame.grid(row=2, column=0, sticky="nsew")
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)

        step_frames = []

        f0 = tk.Frame(content_frame, bg="white")
        f0.columnconfigure(0, weight=1)
        tk.Label(f0, text=APP_NAME, font=("Segoe UI", 18, "bold"), bg="white", fg="#0f172a").pack(pady=(20,4))
        tk.Label(f0, text="Professional Lead Management System", font=("Segoe UI", 10), bg="white", fg="#475569").pack(pady=(0,12))
        tk.Label(f0, text="This installer will guide you through the installation.\nA smart automation platform for lead collection.", font=("Segoe UI", 9), bg="white", fg="#334155", justify="center").pack(pady=4, padx=16)
        features_frame = tk.Frame(f0, bg="#f8fafc", relief="solid", bd=1)
        features_frame.pack(pady=12, padx=20, fill="both", expand=True)
        tk.Label(features_frame, text="Key Features", font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#0f172a").pack(anchor="w", padx=12, pady=(8,4))
        for feat in ["Automated ad monitoring and lead extraction","Intelligent messaging and negotiation assistant","Multi-account and multi-platform support","Secure data management with backup options","Native Windows application with offline capabilities"]:
            tk.Label(features_frame, text=f"• {feat}", font=("Segoe UI", 8), bg="#f8fafc", fg="#475569", anchor="w", justify="left").pack(anchor="w", padx=16, pady=1, fill="x")
        tk.Label(f0, text="Click Next to continue.", font=("Segoe UI", 8), bg="white", fg="#64748b").pack(pady=8)
        step_frames.append(f0)

        f1 = tk.Frame(content_frame, bg="white")
        f1.columnconfigure(0, weight=1)
        f1.rowconfigure(1, weight=1)
        tk.Label(f1, text="License Agreement", font=("Segoe UI", 12, "bold"), bg="white", fg="#0f172a").grid(row=0, column=0, sticky="w", padx=16, pady=(12,6))
        txt_license = tk.Text(f1, font=("Segoe UI", 8), wrap="word", bg="#f8fafc", relief="solid", bd=1)
        txt_license.grid(row=1, column=0, sticky="nsew", padx=16, pady=4)
        txt_license.insert("1.0", f"{APP_NAME} {APP_VERSION}\nEND-USER LICENSE AGREEMENT\n\n1. GRANT - Personal and commercial use per laws.\n2. RESTRICTIONS - No unlawful purposes.\n3. PRIVACY - Local storage, user backup.\n4. COMPONENTS - Chromium and AI under licenses.\n5. DISCLAIMER - As-is.\n6. ACCEPTANCE - Installing means acceptance.\n\n© 2024-2026 Divar Marketing\n")
        txt_license.configure(state="disabled")
        tk.Checkbutton(f1, text="I accept the terms of the license agreement", variable=agree_var, font=("Segoe UI", 9), bg="white", fg="#0f172a").grid(row=2, column=0, sticky="w", padx=16, pady=8)
        step_frames.append(f1)

        f2 = tk.Frame(content_frame, bg="white")
        f2.columnconfigure(0, weight=1)
        tk.Label(f2, text="Previous Installation Data", font=("Segoe UI", 12, "bold"), bg="white", fg="#0f172a").pack(anchor="w", padx=16, pady=(12,6))
        prev_info = has_previous_data()
        if prev_info["exists"]:
            info_text = f"Existing installation detected.\nAccounts: {prev_info['accounts']} | Leads: {prev_info['leads']} | Size: {prev_info['size_mb']} MB\n\nChoose how to handle existing data:"
            bg_color = "#fef3c7"
            fg_color = "#92400e"
        else:
            info_text = "No previous installation found. Fresh installation will be performed."
            bg_color = "#dcfce7"
            fg_color = "#166534"
        wrap_len = max(400, ww - 80)
        tk.Label(f2, text=info_text, font=("Segoe UI", 9), bg=bg_color, fg=fg_color, justify="left", wraplength=wrap_len, padx=12, pady=10).pack(fill="x", padx=16, pady=6)
        preserve_frame = tk.Frame(f2, bg="white")
        preserve_frame.pack(fill="both", expand=True, padx=16, pady=8)
        tk.Radiobutton(preserve_frame, text="Keep all data (Recommended)", variable=preserve_var, value="keep", font=("Segoe UI", 9, "bold"), bg="white", fg="#0f172a").pack(anchor="w", pady=2)
        tk.Label(preserve_frame, text="Preserve accounts, leads, settings, sessions", font=("Segoe UI", 8), bg="white", fg="#64748b").pack(anchor="w", padx=20, pady=(0,6))
        tk.Radiobutton(preserve_frame, text="Keep accounts only", variable=preserve_var, value="keep_accounts", font=("Segoe UI", 9), bg="white", fg="#0f172a").pack(anchor="w", pady=2)
        tk.Label(preserve_frame, text="Preserve logins but clear leads database", font=("Segoe UI", 8), bg="white", fg="#64748b").pack(anchor="w", padx=20, pady=(0,6))
        tk.Radiobutton(preserve_frame, text="Remove all existing data", variable=preserve_var, value="delete_all", font=("Segoe UI", 9), bg="white", fg="#0f172a").pack(anchor="w", pady=2)
        tk.Label(preserve_frame, text="Clean installation (irreversible)", font=("Segoe UI", 8), bg="white", fg="#64748b").pack(anchor="w", padx=20)
        if not prev_info["exists"]:
            preserve_var.set("keep")
            for child in preserve_frame.winfo_children():
                if isinstance(child, tk.Radiobutton):
                    child.configure(state="disabled")
        step_frames.append(f2)

        f3 = tk.Frame(content_frame, bg="white")
        f3.columnconfigure(0, weight=1)
        tk.Label(f3, text="Choose Install Location", font=("Segoe UI", 12, "bold"), bg="white", fg="#0f172a").pack(anchor="w", padx=16, pady=(12,6))
        tk.Label(f3, text="Select the folder where the application will be installed:", font=("Segoe UI", 9), bg="white", fg="#334155", wraplength=wrap_len).pack(anchor="w", padx=16, pady=2)
        path_row = tk.Frame(f3, bg="white")
        path_row.pack(fill="x", padx=16, pady=8)
        path_row.columnconfigure(0, weight=1)
        ent = tk.Entry(path_row, textvariable=install_dir_var, font=("Consolas", 9), bg="white", relief="solid", bd=1)
        ent.grid(row=0, column=0, sticky="ew", ipady=5)
        def browse():
            picked = filedialog.askdirectory(title="Select installation folder", initialdir=install_dir_var.get() or str(Path.home()))
            if picked:
                install_dir_var.set(picked)
        tk.Button(path_row, text="Browse...", command=browse, width=10, font=("Segoe UI", 8), bg="#f1f5f9", relief="solid", bd=1).grid(row=0, column=1, padx=(8,0), ipady=3)
        tk.Label(f3, text="Space required: 500 MB - 2.5 GB\nDefault location does not require admin privileges", font=("Segoe UI", 8), bg="white", fg="#64748b", justify="left", wraplength=wrap_len).pack(anchor="w", padx=16, pady=8)
        step_frames.append(f3)

        f4 = tk.Frame(content_frame, bg="white")
        f4.columnconfigure(0, weight=1)
        tk.Label(f4, text="Select Components", font=("Segoe UI", 12, "bold"), bg="white", fg="#0f172a").pack(anchor="w", padx=16, pady=(12,6))
        tk.Label(f4, text="Choose which components to install:", font=("Segoe UI", 9), bg="white", fg="#334155").pack(anchor="w", padx=16, pady=2)
        comp_frame = tk.Frame(f4, bg="white")
        comp_frame.pack(fill="both", expand=True, padx=16, pady=8)
        tk.Checkbutton(comp_frame, text="Chromium Browser Engine (Recommended)", variable=comp_chrome_var, font=("Segoe UI", 9, "bold"), bg="white", fg="#0f172a").pack(anchor="w", pady=3)
        tk.Label(comp_frame, text="Isolated browser profiles - no interference", font=("Segoe UI", 8), bg="white", fg="#64748b", wraplength=wrap_len).pack(anchor="w", padx=20, pady=(0,6))
        tk.Checkbutton(comp_frame, text="AI Assistant Model", variable=comp_model_var, font=("Segoe UI", 9), bg="white", fg="#0f172a").pack(anchor="w", pady=3)
        tk.Label(comp_frame, text="Local AI model - works offline", font=("Segoe UI", 8), bg="white", fg="#64748b", wraplength=wrap_len).pack(anchor="w", padx=20, pady=(0,6))
        tk.Checkbutton(comp_frame, text="Desktop and Start Menu shortcuts", variable=comp_shortcut_var, font=("Segoe UI", 9), bg="white", fg="#0f172a").pack(anchor="w", pady=3)
        step_frames.append(f4)

        f5 = tk.Frame(content_frame, bg="white")
        f5.columnconfigure(0, weight=1)
        f5.rowconfigure(3, weight=1)
        tk.Label(f5, text="Installing...", font=("Segoe UI", 12, "bold"), bg="white", fg="#0f172a").grid(row=0, column=0, sticky="w", padx=16, pady=(12,4))
        status_label = tk.Label(f5, text="Preparing installation...", font=("Segoe UI", 9), bg="white", fg="#334155", wraplength=wrap_len, anchor="w", justify="left")
        status_label.grid(row=1, column=0, sticky="ew", padx=16, pady=2)
        bar = ttk.Progressbar(f5, mode="determinate", maximum=100)
        bar.grid(row=2, column=0, sticky="ew", padx=16, pady=8)
        log_frame = tk.Frame(f5, bg="white")
        log_frame.grid(row=3, column=0, sticky="nsew", padx=16, pady=6)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)
        tk.Label(log_frame, text="Installation details:", font=("Segoe UI", 8, "bold"), bg="white", fg="#475569").grid(row=0, column=0, sticky="w")
        logbox = tk.Text(log_frame, font=("Consolas", 7), bg="#0f172a", fg="#e2e8f0", relief="flat", wrap="word")
        logbox.grid(row=1, column=0, sticky="nsew", pady=4)

        def log(msg: str):
            def _do():
                try:
                    logbox.configure(state="normal")
                    logbox.insert("end", f"{msg}\n")
                    logbox.see("end")
                    logbox.configure(state="disabled")
                except:
                    pass
            try:
                root.after(0, _do)
            except:
                pass

        def prog(pct: int, label: str):
            def _do():
                try:
                    bar["value"] = pct
                    status_label.configure(text=label)
                except:
                    pass
            try:
                root.after(0, _do)
            except:
                pass

        step_frames.append(f5)

        f6 = tk.Frame(content_frame, bg="white")
        f6.columnconfigure(0, weight=1)
        tk.Label(f6, text="Done", font=("Segoe UI", 36), bg="white", fg="#16a34a").pack(pady=(20,4))
        tk.Label(f6, text="Installation Complete", font=("Segoe UI", 14, "bold"), bg="white", fg="#0f172a").pack(pady=2)
        tk.Label(f6, text=f"{APP_NAME} has been successfully installed.\n\nShortcuts created on Desktop and Start Menu.", font=("Segoe UI", 9), bg="white", fg="#334155", justify="center", wraplength=wrap_len).pack(pady=10, padx=16)
        launch_var = tk.BooleanVar(value=True)
        tk.Checkbutton(f6, text="Launch application now", variable=launch_var, font=("Segoe UI", 9, "bold"), bg="white", fg="#0f172a").pack(pady=10)
        step_frames.append(f6)

        def show_step(idx: int):
            for i, fr in enumerate(step_frames):
                if i == idx:
                    fr.grid(row=0, column=0, sticky="nsew")
                    fr.tkraise()
                else:
                    fr.grid_remove()
            for i, lbl in enumerate(step_labels):
                if i == idx:
                    lbl.configure(font=("Segoe UI", 8, "bold"), fg="#2563eb")
                elif i < idx:
                    lbl.configure(font=("Segoe UI", 7), fg="#16a34a")
                else:
                    lbl.configure(font=("Segoe UI", 7), fg="#64748b")
            if idx == 0:
                btn_back.configure(state="disabled")
                btn_next.configure(text="Next >", state="normal")
                btn_install.grid_remove()
                btn_finish.grid_remove()
            elif idx in (1,2,3,4):
                btn_back.configure(state="normal")
                btn_next.configure(text="Next >", state="normal")
                btn_install.grid_remove()
                btn_finish.grid_remove()
                if idx == 4:
                    btn_next.configure(text="Install", state="normal")
            elif idx == 5:
                btn_back.configure(state="disabled")
                btn_next.configure(state="disabled")
                btn_install.grid_remove()
                btn_finish.grid_remove()
            elif idx == 6:
                btn_back.configure(state="disabled")
                btn_next.configure(state="disabled")
                btn_install.grid_remove()
                btn_finish.grid(row=0, column=2, padx=12, pady=8)

        btn_frame = tk.Frame(main_frame, bg="#f8fafc", height=48)
        btn_frame.grid(row=3, column=0, sticky="ew")
        btn_frame.grid_propagate(False)
        btn_frame.columnconfigure(1, weight=1)

        btn_finish = tk.Button(btn_frame, text="Finish", width=12, font=("Segoe UI", 9, "bold"), bg="#16a34a", fg="white", relief="flat", padx=8, pady=4, command=lambda: root.destroy())
        btn_back = tk.Button(btn_frame, text="< Back", width=9, font=("Segoe UI", 8), bg="white", relief="solid", bd=1)
        btn_next = tk.Button(btn_frame, text="Next >", width=9, font=("Segoe UI", 8, "bold"), bg="#2563eb", fg="white", relief="flat")
        btn_install = tk.Button(btn_frame, text="Install", width=12, font=("Segoe UI", 9, "bold"), bg="#2563eb", fg="white", relief="flat")

        btn_back.grid(row=0, column=0, padx=12, pady=8, sticky="w")
        btn_next.grid(row=0, column=2, padx=8, pady=8, sticky="e")
        btn_install.grid(row=0, column=2, padx=8, pady=8, sticky="e")
        btn_finish.grid(row=0, column=2, padx=12, pady=8, sticky="e")
        btn_finish.grid_remove()
        btn_install.grid_remove()

        def on_back():
            if current_step[0] > 0:
                current_step[0] -= 1
                show_step(current_step[0])

        def on_next():
            idx = current_step[0]
            if idx == 1 and not agree_var.get():
                messagebox.showwarning("License Agreement", "Please accept the license agreement to continue.")
                return
            if idx == 2:
                if preserve_var.get() == "delete_all":
                    if not messagebox.askyesno("Confirm Deletion", "Are you sure you want to delete all existing data?\n\nThis action cannot be undone."):
                        return
            if idx == 3:
                dest = install_dir_var.get().strip()
                if not dest:
                    messagebox.showwarning("Location", "Please select an installation location.")
                    return
            if idx == 4:
                current_step[0] = 5
                show_step(5)
                def work():
                    try:
                        chosen = Path(install_dir_var.get().strip() or str(default_install_dir()))
                        log(f"Install location: {chosen}")
                        prog(5, "Preparing installation directory...")
                        chosen.mkdir(parents=True, exist_ok=True)
                        prog(15, f"Handling existing data: {preserve_var.get()}...")
                        target = extract_payload(chosen, log, progress_cb=lambda p, l: prog(15+int(p*0.7), l), preserve_mode=preserve_var.get())
                        prog(85, "Creating shortcuts...")
                        if comp_shortcut_var.get():
                            ico = app_icon()
                            ico_dst = chosen / "app.ico"
                            if ico.exists():
                                shutil.copy2(ico, ico_dst)
                            make_shortcut(target, chosen, ico_dst if ico_dst.exists() else ico, log)
                        prog(90, "Configuring firewall...")
                        open_firewall(log)
                        prog(95, "Finalizing installation...")
                        if launch_var.get():
                            launch(target, chosen, log)
                        prog(100, "Installation completed successfully")
                        log("Installation completed")
                        current_step[0] = 6
                        root.after(0, lambda: show_step(6))
                    except Exception as e:
                        log(f"Error: {e}")
                        log(traceback.format_exc())
                        root.after(0, lambda: messagebox.showerror("Installation Failed", f"Installation failed:\n{e}"))
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

    except Exception as e:
        print(f"GUI crash: {e}")
        traceback.print_exc()
        try:
            import tkinter.messagebox as mb
            mb.showerror("Setup Crash", f"Setup crashed:\n{e}\n\n{traceback.format_exc()[:1000]}")
        except:
            pass
        return 1

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
        target = extract_payload(Path(dest), print, preserve_mode=preserve)
        make_shortcut(target, Path(dest), app_icon(), print)
        open_firewall(print)
        launch(target, Path(dest), print)
        return 0
    return gui_wizard()

if __name__ == "__main__":
    raise SystemExit(main())
