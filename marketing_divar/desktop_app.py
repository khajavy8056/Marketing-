# -*- coding: utf-8 -*-
"""Divar Marketing - Professional Native Desktop v4.3
Clean commercial native Windows application - no internal test notes
"""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Callable, Optional

from .paths import apply_runtime_paths, user_data_dir
from .brand import APP_NAME_EN, APP_NAME_FA, PORT

APP_TITLE = f"{APP_NAME_FA} - {APP_NAME_EN}"
VERSION = "4.3.0-professional"

_server_thread: Optional[threading.Thread] = None
_server_port: int = PORT
_server_running: bool = False

def _ensure_runtime() -> Path:
    dest = apply_runtime_paths()
    for sub in ("accounts", "logs", "app-chromium", "nlu-model", "data"):
        (dest / sub).mkdir(parents=True, exist_ok=True)
    try:
        from .db import connect, init_db
        alt_path = dest / "data" / "divar_leads.db"
        (dest / "data").mkdir(parents=True, exist_ok=True)
        if not alt_path.exists():
            con = connect(str(alt_path))
            try:
                init_db(con)
            except:
                pass
            finally:
                try:
                    con.close()
                except:
                    pass
    except:
        pass
    if sys.platform == "win32":
        try:
            import subprocess
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "add", "rule",
                 f"name={APP_NAME_EN}", "dir=in", "action=allow",
                 "protocol=TCP", f"localport={PORT}"],
                capture_output=True, timeout=8)
        except:
            pass
    return dest

def _start_server_bg(log_fn: Optional[Callable[[str], None]] = None) -> int:
    global _server_thread, _server_port, _server_running
    from .web.server import app, start_background
    import uvicorn
    import socket

    host = "127.0.0.1"
    port = PORT

    def _free(p: int) -> bool:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((host, p))
            s.close()
            return True
        except OSError:
            return False

    for _ in range(10):
        if _free(port):
            break
        port += 1

    _server_port = port
    start_background()

    def _run():
        global _server_running
        _server_running = True
        try:
            uvicorn.run(app, host=host, port=port, log_level="warning")
        except Exception as e:
            if log_fn:
                log_fn(f"Server: {e}")
            _server_running = False

    th = threading.Thread(target=_run, daemon=True, name="Server")
    th.start()
    _server_thread = th

    for _ in range(80):
        time.sleep(0.5)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect((host, port))
            s.close()
            if log_fn:
                log_fn(f"Server ready on port {port}")
            break
        except:
            continue

    return port

def _check_deps_with_progress(log_fn: Callable[[str], None], 
                               chrome_cb: Callable[[int, str, str], None],
                               model_cb: Callable[[int, str, str], None]):
    try:
        from .app_chromium import is_ready, status, start_install_async
        chrome_cb(5, "Chromium: Checking...", "—")
        if not is_ready():
            log_fn("Chromium not installed - starting download...")
            try:
                start_install_async()
                for i in range(120):
                    time.sleep(1)
                    st = status()
                    pct = int(st.get("percent") or 0)
                    note = st.get("note") or st.get("message") or "Downloading..."
                    if pct > 0:
                        chrome_cb(pct, f"Chromium: {note} {pct}%", st.get("speed") or "—")
                    if st.get("installed") or st.get("ready"):
                        chrome_cb(100, "Chromium: Ready", "—")
                        log_fn("Chromium ready")
                        break
            except Exception as e:
                log_fn(f"Chromium: {e}")
                chrome_cb(30, f"Chromium: {e}", "—")
        else:
            st = status()
            chrome_cb(100, "Chromium: Ready", "—")
            log_fn("Chromium ready")
    except Exception as e:
        log_fn(f"Chromium: {e}")
        chrome_cb(0, f"Chromium error: {e}", "—")

    try:
        from .nlu_model import is_ready, status, start_install_async
        model_cb(5, "AI Model: Checking...", "—")
        if not is_ready():
            log_fn("AI Model not installed - starting download...")
            try:
                start_install_async()
                for i in range(120):
                    time.sleep(1)
                    st = status()
                    pct = int(st.get("percent") or 0)
                    note = st.get("note") or st.get("backend") or "Downloading..."
                    if pct > 0:
                        model_cb(pct, f"AI Model: {note} {pct}%", st.get("speed") or "—")
                    if st.get("ready") or st.get("installed"):
                        model_cb(100, f"AI Model: Ready ({st.get('backend','')})", "—")
                        log_fn(f"AI Model ready: {st.get('backend')}")
                        break
            except Exception as e:
                log_fn(f"AI Model: {e} - using fallback")
                model_cb(50, f"AI Model: Fallback mode", "—")
        else:
            st = status()
            model_cb(100, f"AI Model: Ready ({st.get('backend','')})", "—")
            log_fn(f"AI Model ready: {st.get('backend')}")
    except Exception as e:
        log_fn(f"AI Model: {e}")
        model_cb(0, f"Model error: {e}", "—")

def _create_native_gui():
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox, scrolledtext
    except Exception as e:
        print(f"Tkinter not available: {e}")
        url = f"http://127.0.0.1:{_server_port}"
        webbrowser.open(url)
        return

    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("1100x750")
    root.minsize(960, 600)
    root.configure(bg="#f8fafc")
    
    try:
        ico = Path(__file__).resolve().parent.parent / "installer" / "app.ico"
        if ico.exists():
            root.iconbitmap(default=str(ico))
    except:
        pass

    style = ttk.Style()
    try:
        style.theme_use("vista")
    except:
        pass
    style.configure("TProgressbar", thickness=18, troughcolor="#e5e7eb", background="#2563eb")

    main_frame = tk.Frame(root, bg="#f8fafc")
    main_frame.pack(fill="both", expand=True)
    main_frame.columnconfigure(0, weight=1)
    main_frame.rowconfigure(1, weight=1)

    header = tk.Frame(main_frame, bg="#1e293b", height=64)
    header.grid(row=0, column=0, sticky="ew")
    header.grid_propagate(False)
    header.columnconfigure(1, weight=1)

    tk.Label(header, text=APP_NAME_FA, font=("Segoe UI", 14, "bold"), bg="#1e293b", fg="white").grid(row=0, column=0, sticky="w", padx=20, pady=8)
    tk.Label(header, text=APP_NAME_EN, font=("Segoe UI", 9), bg="#1e293b", fg="#94a3b8").grid(row=1, column=0, sticky="w", padx=20)

    status_var = tk.StringVar(value="Initializing...")
    tk.Label(header, textvariable=status_var, font=("Segoe UI", 9), bg="#1e293b", fg="#38bdf8").grid(row=0, column=1, rowspan=2, padx=20)

    server_status_var = tk.StringVar(value="Server: Starting")
    tk.Label(header, textvariable=server_status_var, font=("Segoe UI", 9), bg="#1e293b", fg="#fbbf24").grid(row=0, column=2, rowspan=2, sticky="e", padx=20)

    notebook = ttk.Notebook(main_frame)
    notebook.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)

    # Tab 1: Dashboard
    tab_dash = tk.Frame(notebook, bg="white")
    notebook.add(tab_dash, text="Dashboard")
    
    dash_frame = tk.Frame(tab_dash, bg="white")
    dash_frame.pack(fill="both", expand=True, padx=16, pady=16)
    
    stats_frame = tk.Frame(dash_frame, bg="#f8fafc", relief="solid", bd=1)
    stats_frame.pack(fill="x", pady=(0,12))
    
    tk.Label(stats_frame, text="System Status", font=("Segoe UI", 11, "bold"), bg="#f8fafc", fg="#0f172a").pack(anchor="w", padx=16, pady=8)
    
    stats_grid = tk.Frame(stats_frame, bg="#f8fafc")
    stats_grid.pack(fill="x", padx=16, pady=10)
    
    stat_labels = {}
    stats = [("total_leads", "Total Leads", "0"), ("phones_found", "With Phone", "0"), ("queue", "Queue", "0"), ("running", "Monitor", "Stopped")]
    for i, (key, title, default) in enumerate(stats):
        f = tk.Frame(stats_grid, bg="white", relief="solid", bd=1)
        f.grid(row=0, column=i, padx=6, pady=6, sticky="ew")
        stats_grid.columnconfigure(i, weight=1)
        tk.Label(f, text=title, font=("Segoe UI", 9), bg="white", fg="#64748b").pack(pady=(10,2))
        lbl = tk.Label(f, text=default, font=("Segoe UI", 14, "bold"), bg="white", fg="#0f172a")
        lbl.pack(pady=(0,10))
        stat_labels[key] = lbl

    ctrl_frame = tk.Frame(dash_frame, bg="white")
    ctrl_frame.pack(fill="x", pady=10)
    
    def start_monitor():
        try:
            import requests
            r = requests.post(f"http://127.0.0.1:{_server_port}/api/monitor/start", json={"include_existing": False}, timeout=10)
            if r.status_code == 200:
                messagebox.showinfo("Success", "Monitoring started")
                status_var.set("Monitor: Running")
            else:
                messagebox.showwarning("Warning", f"Error: {r.text[:200]}")
        except Exception as e:
            messagebox.showerror("Error", f"{e}")

    def stop_monitor():
        try:
            import requests
            r = requests.post(f"http://127.0.0.1:{_server_port}/api/monitor/stop", timeout=10)
            if r.status_code == 200:
                messagebox.showinfo("Success", "Monitoring stopped")
                status_var.set("Monitor: Stopped")
            else:
                messagebox.showwarning("Warning", f"{r.text[:200]}")
        except Exception as e:
            messagebox.showerror("Error", f"{e}")

    def open_browser_panel():
        url = f"http://127.0.0.1:{_server_port}"
        webbrowser.open(url)
        status_var.set(f"Full panel opened in browser")

    tk.Button(ctrl_frame, text="Start Monitoring", font=("Segoe UI", 10, "bold"), bg="#16a34a", fg="white", relief="flat", padx=20, pady=8, command=start_monitor).pack(side="left", padx=6)
    tk.Button(ctrl_frame, text="Stop", font=("Segoe UI", 10), bg="#e2e8f0", relief="flat", padx=16, pady=8, command=stop_monitor).pack(side="left", padx=6)
    tk.Button(ctrl_frame, text="Open Full Panel in Browser", font=("Segoe UI", 10), bg="#2563eb", fg="white", relief="flat", padx=16, pady=8, command=open_browser_panel).pack(side="left", padx=16)

    log_frame_dash = tk.LabelFrame(dash_frame, text="Live Log", font=("Segoe UI", 9, "bold"), bg="white")
    log_frame_dash.pack(fill="both", expand=True, pady=10)
    log_text_dash = scrolledtext.ScrolledText(log_frame_dash, font=("Consolas", 8), bg="#0f172a", fg="#e2e8f0", height=14)
    log_text_dash.pack(fill="both", expand=True, padx=6, pady=6)

    # Tab 2: Assistant
    tab_tira = tk.Frame(notebook, bg="white")
    notebook.add(tab_tira, text="Assistant")

    tira_frame = tk.Frame(tab_tira, bg="white")
    tira_frame.pack(fill="both", expand=True, padx=12, pady=12)
    tira_frame.columnconfigure(0, weight=1)
    tira_frame.rowconfigure(0, weight=1)

    tira_chat = scrolledtext.ScrolledText(tira_frame, font=("Segoe UI", 10), bg="#f8fafc", fg="#0f172a", wrap="word", height=20)
    tira_chat.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0,10))
    tira_chat.insert("1.0", "Welcome to Divar Marketing Assistant\n\nI can help you with:\n• Setting up search keywords and categories\n• Configuring message templates\n• Managing SMS and chat automation\n• Monitoring system status\n\nType your request below to get started.\n\n")
    tira_chat.configure(state="disabled")

    tira_input_frame = tk.Frame(tira_frame, bg="white")
    tira_input_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
    tira_input_frame.columnconfigure(0, weight=1)

    tira_entry_var = tk.StringVar()
    tira_entry = tk.Entry(tira_input_frame, textvariable=tira_entry_var, font=("Segoe UI", 10), bg="white", relief="solid", bd=1)
    tira_entry.grid(row=0, column=0, sticky="ew", ipady=8, padx=(0,10))

    def send_to_tira():
        msg = tira_entry_var.get().strip()
        if not msg:
            return
        tira_chat.configure(state="normal")
        tira_chat.insert("end", f"\nYou: {msg}\n")
        tira_chat.configure(state="disabled")
        tira_chat.see("end")
        tira_entry_var.set("")

        def _call_tira():
            try:
                import requests
                r = requests.post(f"http://127.0.0.1:{_server_port}/api/tira/agent", 
                                  json={"message": msg, "session_id": "desktop"}, timeout=30)
                if r.status_code == 200:
                    data = r.json()
                    reply = data.get("reply") or data.get("message") or str(data)
                    def _show():
                        tira_chat.configure(state="normal")
                        tira_chat.insert("end", f"\nAssistant: {reply}\n{'-'*50}\n")
                        tira_chat.configure(state="disabled")
                        tira_chat.see("end")
                    root.after(0, _show)
                else:
                    def _err():
                        tira_chat.configure(state="normal")
                        tira_chat.insert("end", f"\nError: {r.text[:500]}\n")
                        tira_chat.configure(state="disabled")
                        tira_chat.see("end")
                    root.after(0, _err)
            except Exception as e:
                def _exc():
                    tira_chat.configure(state="normal")
                    tira_chat.insert("end", f"\nError: {e}\n")
                    tira_chat.configure(state="disabled")
                    tira_chat.see("end")
                root.after(0, _exc)

        threading.Thread(target=_call_tira, daemon=True).start()

    def tira_entry_key(event):
        if event.keysym == "Return":
            send_to_tira()

    tira_entry.bind("<KeyPress>", tira_entry_key)
    tk.Button(tira_input_frame, text="Send", font=("Segoe UI", 10, "bold"), bg="#2563eb", fg="white", relief="flat", padx=20, pady=8, command=send_to_tira).grid(row=0, column=1)

    quick_frame = tk.Frame(tira_frame, bg="white")
    quick_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=10)
    quick_msgs = [
        "How to setup SMS panel?",
        "Search all mobile ads",
        "Configure message template",
        "Check system status",
        "Setup Telegram bot",
    ]
    for qm in quick_msgs:
        btn = tk.Button(quick_frame, text=qm, font=("Segoe UI", 8), bg="#f1f5f9", relief="flat", padx=10, pady=5,
                        command=lambda m=qm: (tira_entry_var.set(m), send_to_tira()))
        btn.pack(side="left", padx=4, pady=2)

    # Tab 3: Downloads
    tab_deps = tk.Frame(notebook, bg="white")
    notebook.add(tab_deps, text="Components")

    deps_frame = tk.Frame(tab_deps, bg="white")
    deps_frame.pack(fill="both", expand=True, padx=20, pady=20)

    tk.Label(deps_frame, text="Component Status", font=("Segoe UI", 12, "bold"), bg="white", fg="#0f172a").pack(anchor="w", pady=(0,16))

    chrome_dep_frame = tk.LabelFrame(deps_frame, text="Chromium Engine", font=("Segoe UI", 10, "bold"), bg="white", padx=16, pady=12)
    chrome_dep_frame.pack(fill="x", pady=10)
    chrome_label_var = tk.StringVar(value="Chromium: Checking...")
    tk.Label(chrome_dep_frame, textvariable=chrome_label_var, font=("Segoe UI", 10), bg="white", fg="#334155", anchor="w").pack(fill="x")
    chrome_bar = ttk.Progressbar(chrome_dep_frame, mode="determinate", maximum=100)
    chrome_bar.pack(fill="x", pady=6)
    chrome_speed_var = tk.StringVar(value="—")
    tk.Label(chrome_dep_frame, textvariable=chrome_speed_var, font=("Consolas", 9), bg="white", fg="#64748b", anchor="w").pack(fill="x")

    model_dep_frame = tk.LabelFrame(deps_frame, text="AI Model", font=("Segoe UI", 10, "bold"), bg="white", padx=16, pady=12)
    model_dep_frame.pack(fill="x", pady=10)
    model_label_var = tk.StringVar(value="AI Model: Checking...")
    tk.Label(model_dep_frame, textvariable=model_label_var, font=("Segoe UI", 10), bg="white", fg="#334155", anchor="w").pack(fill="x")
    model_bar = ttk.Progressbar(model_dep_frame, mode="determinate", maximum=100)
    model_bar.pack(fill="x", pady=6)
    model_speed_var = tk.StringVar(value="—")
    tk.Label(model_dep_frame, textvariable=model_speed_var, font=("Consolas", 9), bg="white", fg="#64748b", anchor="w").pack(fill="x")

    deps_log_frame = tk.LabelFrame(deps_frame, text="Log", font=("Segoe UI", 9, "bold"), bg="white")
    deps_log_frame.pack(fill="both", expand=True, pady=16)
    deps_log = scrolledtext.ScrolledText(deps_log_frame, font=("Consolas", 8), bg="#0f172a", fg="#e2e8f0", height=10)
    deps_log.pack(fill="both", expand=True, padx=6, pady=6)

    def deps_log_fn(msg: str):
        def _do():
            deps_log.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            deps_log.see("end")
            log_text_dash.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            log_text_dash.see("end")
        try:
            root.after(0, _do)
        except:
            print(msg)

    def chrome_cb(pct: int, text: str, speed: str):
        def _do():
            chrome_bar["value"] = pct
            chrome_label_var.set(text)
            chrome_speed_var.set(f"Speed: {speed}")
        try:
            root.after(0, _do)
        except:
            pass

    def model_cb(pct: int, text: str, speed: str):
        def _do():
            model_bar["value"] = pct
            model_label_var.set(text)
            model_speed_var.set(f"Speed: {speed}")
        try:
            root.after(0, _do)
        except:
            pass

    # Tab 4: Settings
    tab_settings = tk.Frame(notebook, bg="white")
    notebook.add(tab_settings, text="Settings")

    settings_frame = tk.Frame(tab_settings, bg="white")
    settings_frame.pack(fill="both", expand=True, padx=20, pady=20)
    tk.Label(settings_frame, text="Settings", font=("Segoe UI", 12, "bold"), bg="white", fg="#0f172a").pack(anchor="w", pady=(0,16))
    tk.Label(settings_frame, text="For full configuration, open the complete panel in browser:\n• Keywords and categories\n• Message templates\n• SMS gateway (username, password, line, pattern)\n• Telegram, Bale, Rubika bots\n• IP and quota management\n• Account management\n\nThis native window provides quick control and assistant chat.\nThe full web panel is available via the button in Dashboard.", 
             font=("Segoe UI", 10), bg="white", fg="#334155", justify="left").pack(anchor="w", pady=10)

    bottom_bar = tk.Frame(main_frame, bg="#f1f5f9", height=28)
    bottom_bar.grid(row=2, column=0, sticky="ew")
    bottom_bar.grid_propagate(False)
    tk.Label(bottom_bar, text=f"{APP_NAME_FA} - v{VERSION} - Professional Edition", font=("Segoe UI", 8), bg="#f1f5f9", fg="#64748b").pack(side="left", padx=16, pady=6)
    tk.Label(bottom_bar, text=f"Data: {user_data_dir()}", font=("Consolas", 7), bg="#f1f5f9", fg="#94a3b8").pack(side="right", padx=16)

    def server_monitor():
        while True:
            time.sleep(2)
            try:
                import requests
                r = requests.get(f"http://127.0.0.1:{_server_port}/api/status", timeout=3)
                if r.status_code == 200:
                    data = r.json()
                    def _upd():
                        server_status_var.set("Server: Running")
                        stat_labels["total_leads"].configure(text=str(data.get("total_leads", 0)))
                        stat_labels["phones_found"].configure(text=str(data.get("phones_found", 0)))
                        stat_labels["queue"].configure(text=str(data.get("queue", 0)))
                        stat_labels["running"].configure(text="Running" if data.get("running") else "Stopped")
                        status_var.set(f"Monitor: {'Running' if data.get('running') else 'Stopped'} | Leads: {data.get('total_leads',0)}")
                    root.after(0, _upd)
                else:
                    root.after(0, lambda: server_status_var.set("Server: Error"))
            except:
                root.after(0, lambda: server_status_var.set("Server: Offline"))

    def deps_worker():
        time.sleep(1)
        _check_deps_with_progress(deps_log_fn, chrome_cb, model_cb)

    threading.Thread(target=server_monitor, daemon=True).start()
    threading.Thread(target=deps_worker, daemon=True).start()

    deps_log_fn(f"{APP_TITLE} v{VERSION} started")
    deps_log_fn(f"Data: {user_data_dir()}")
    deps_log_fn(f"Server: http://127.0.0.1:{_server_port}")

    root.mainloop()

def main():
    data_dir = _ensure_runtime()
    port = _start_server_bg(log_fn=print)
    _create_native_gui()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
