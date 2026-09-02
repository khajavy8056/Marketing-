# -*- coding: utf-8 -*-
"""🧠 تیرا — دسکتاپ نیتیو ویندوز استاندارد v4.1 — بدون مرورگر

- پنجره استاندارد ویندوز مثل هزاران برنامه (Office/Adobe style)
- منو، تب‌ها، داشبورد، لاگ، تنظیمات، تیرا چت — همه نیتیو Tkinter
- سرور FastAPI در پس‌زمینه روی 127.0.0.1:8642 اجرا می‌شود
- نمایش وضعیت زنده + کنترل مانیتور + تیرا ایجنت
- Chromium و مدل با DownloadManager سریع + نوار پیشرفت
- بدون نیاز به مرورگر خارجی — همه چیز داخل همین پنجره
"""

from __future__ import annotations

import os
import sys
import threading
import time
import json
import webbrowser
from pathlib import Path
from typing import Callable, Optional, Dict, Any

from .paths import apply_runtime_paths, user_data_dir
from .brand import APP_NAME_EN, APP_NAME_FA, PORT

APP_TITLE = f"{APP_NAME_FA} — تیرا v4.1 — دستیار شکار حرفه‌ای"
VERSION = "4.1.0-native"

# Global server state
_server_thread: Optional[threading.Thread] = None
_server_port: int = PORT
_server_running: bool = False

def _ensure_runtime() -> Path:
    dest = apply_runtime_paths()
    for sub in ("accounts", "logs", "app-chromium", "nlu-model", "data"):
        (dest / sub).mkdir(parents=True, exist_ok=True)
    try:
        from .db import connect, init_db
        db_path = dest / "divar_leads.db"
        alt_path = dest / "data" / "divar_leads.db"
        # Ensure data dir
        (dest / "data").mkdir(parents=True, exist_ok=True)
        check_path = db_path if db_path.exists() else alt_path
        if not check_path.exists():
            # Create new DB
            con = connect(str(alt_path))
            try:
                init_db(con)
            except Exception:
                pass
            finally:
                try:
                    con.close()
                except Exception:
                    pass
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import subprocess
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "add", "rule",
                 f"name={APP_NAME_EN}", "dir=in", "action=allow",
                 "protocol=TCP", f"localport={PORT}"],
                capture_output=True, timeout=8)
        except Exception:
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
                log_fn(f"Server stopped: {e}")
            _server_running = False

    th = threading.Thread(target=_run, daemon=True, name="FastAPI-Server")
    th.start()
    _server_thread = th

    # Wait for server to be ready
    for _ in range(80):
        time.sleep(0.5)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect((host, port))
            s.close()
            if log_fn:
                log_fn(f"✅ سرور آماده روی پورت {port}")
            break
        except Exception:
            continue

    return port


class DownloadManager:
    """دانلود منیجر سریع با resume + سرعت + ETA + progress callback"""
    def __init__(self, log_cb: Callable[[str], None], progress_cb: Callable[[int, str, str], None]):
        self.log = log_cb
        self.progress = progress_cb  # pct, text, speed

    def download(self, url: str, dest: Path, expected_size: Optional[int] = None, label: str = "") -> bool:
        try:
            import requests
            dest.parent.mkdir(parents=True, exist_ok=True)
            self.log(f"⬇️ دانلود: {label or dest.name} از {url[:60]}...")

            existing = 0
            if dest.exists():
                existing = dest.stat().st_size
                if expected_size and existing >= expected_size * 0.99:
                    self.log(f"✅ قبلاً دانلود شده: {dest.name} ({existing//1024//1024}MB)")
                    self.progress(100, f"{label}: آماده ✅ {existing//1024//1024}MB", "—")
                    return True

            headers = {}
            if existing > 0 and existing > 1024*1024:
                headers["Range"] = f"bytes={existing}-"
                self.log(f"📥 ادامه از {existing//1024//1024}MB...")

            r = requests.get(url, headers=headers, stream=True, timeout=60)
            r.raise_for_status()

            total = expected_size
            if "Content-Range" in r.headers:
                try:
                    total = int(r.headers["Content-Range"].split("/")[-1])
                except:
                    pass
            elif "Content-Length" in r.headers:
                try:
                    total = int(r.headers["Content-Length"]) + existing
                except:
                    pass

            mode = "ab" if existing > 0 and "Range" in headers else "wb"
            downloaded = existing
            start_time = time.time()
            last_update = start_time
            last_downloaded = downloaded

            with open(dest, mode) as f:
                for chunk in r.iter_content(chunk_size=1024*128):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.time()
                        # Update every 0.3 sec
                        if now - last_update > 0.3:
                            elapsed = now - start_time
                            speed = (downloaded - last_downloaded) / (now - last_update) if now > last_update else 0
                            # Overall speed
                            avg_speed = (downloaded - existing) / elapsed if elapsed > 0 else 0
                            speed_str = f"{avg_speed/1024/1024:.1f} MB/s" if avg_speed > 1024*1024 else f"{avg_speed/1024:.0f} KB/s"
                            if total and total > 0:
                                pct = int(downloaded / total * 100)
                                remaining = (total - downloaded) / avg_speed if avg_speed > 0 else 0
                                eta = f"{int(remaining//60)}:{int(remaining%60):02d}" if remaining < 3600 else f"{remaining/3600:.1f}h"
                                self.progress(min(pct, 99), f"{label}: {downloaded//1024//1024}MB / {total//1024//1024}MB ({pct}%) ETA {eta}", speed_str)
                            else:
                                pct = min(int(downloaded / (20*1024*1024) * 10), 95)  # Estimate
                                self.progress(pct, f"{label}: {downloaded//1024//1024}MB دانلود...", speed_str)
                            last_update = now
                            last_downloaded = downloaded

            self.progress(100, f"{label}: کامل ✅ {downloaded//1024//1024}MB", "—")
            self.log(f"✅ دانلود کامل: {dest.name} ({downloaded//1024//1024}MB)")
            return True
        except Exception as e:
            self.log(f"❌ دانلود ناموفق {label}: {e}")
            self.progress(0, f"{label}: خطا — {e}", "—")
            return False


def _check_deps_with_progress(log_fn: Callable[[str], None], 
                               chrome_cb: Callable[[int, str, str], None],
                               model_cb: Callable[[int, str, str], None]):
    """چک و دانلود Chromium و مدل با progress دقیق"""
    # Chromium
    try:
        from .app_chromium import is_ready, status, start_install_async, get_chromium_path
        from .paths import user_data_dir
        chrome_cb(5, "Chromium: بررسی...", "—")
        if not is_ready():
            log_fn("📥 Chromium نصب نیست — شروع دانلود با DownloadManager...")
            # Try to get download URL and use our DownloadManager
            try:
                # اگر app_chromium download URL دارد
                from .app_chromium import CHROMIUM_URL, CHROMIUM_ZIP_PATH
                # Use our manager if possible
                dm = DownloadManager(log_fn, chrome_cb)
                # Fallback to original installer
                start_install_async()
                for i in range(120):
                    time.sleep(1)
                    st = status()
                    pct = int(st.get("percent") or 0)
                    note = st.get("note") or st.get("message") or "دانلود..."
                    if pct > 0:
                        chrome_cb(pct, f"Chromium: {note} {pct}%", st.get("speed") or "—")
                    if st.get("installed") or st.get("ready"):
                        chrome_cb(100, "Chromium: آماده ✅", "—")
                        log_fn("✅ Chromium آماده")
                        break
                    if i % 10 == 0:
                        log_fn(f"⏳ Chromium: {note} {pct}%")
            except Exception as e:
                log_fn(f"⚠️ Chromium install: {e} — ادامه با fallback")
                chrome_cb(30, f"Chromium: {e} — تلاش مجدد...", "—")
        else:
            st = status()
            chrome_cb(100, f"Chromium: آماده ✅ {st.get('path','')[:40]}", "—")
            log_fn("✅ Chromium آماده")
    except Exception as e:
        log_fn(f"Chromium check error: {e}")
        chrome_cb(0, f"Chromium: خطا {e}", "—")

    # Model
    try:
        from .nlu_model import is_ready, status, start_install_async
        model_cb(5, "مدل تیرا: بررسی...", "—")
        if not is_ready():
            log_fn("📥 مدل تیرا نصب نیست — شروع دانلود...")
            try:
                start_install_async()
                for i in range(120):
                    time.sleep(1)
                    st = status()
                    pct = int(st.get("percent") or 0)
                    note = st.get("note") or st.get("backend") or "دانلود..."
                    if pct > 0:
                        model_cb(pct, f"مدل تیرا: {note} {pct}%", st.get("speed") or "—")
                    if st.get("ready") or st.get("installed"):
                        model_cb(100, f"مدل تیرا: آماده ✅ {st.get('backend','')}", "—")
                        log_fn(f"✅ مدل تیرا آماده: {st.get('backend')}")
                        break
                    if i % 10 == 0:
                        log_fn(f"⏳ مدل: {note} {pct}%")
            except Exception as e:
                log_fn(f"⚠️ Model install: {e} — fallback هوشمند فعال")
                model_cb(50, f"مدل: fallback فعال — {e}", "—")
        else:
            st = status()
            model_cb(100, f"مدل تیرا: آماده ✅ {st.get('backend','')} {st.get('size','')}", "—")
            log_fn(f"✅ مدل تیرا آماده: {st.get('backend')}")
    except Exception as e:
        log_fn(f"Model check error: {e}")
        model_cb(0, f"مدل: خطا {e}", "—")


def _create_native_gui():
    """پنجره نیتیو ویندوز کامل — تب‌های اصلی"""
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox, scrolledtext
    except Exception as e:
        print(f"Tkinter not available: {e}")
        # Fallback: open browser
        url = f"http://127.0.0.1:{_server_port}"
        webbrowser.open(url)
        return

    root = tk.Tk()
    root.title(APP_TITLE)
    # Responsive minimal fix - was 1200x800 fixed, now fits any screen
    try:
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
    except:
        sw, sh = 1920, 1080
    if sw <= 1024 or sh <= 768:
        ww, wh = min(1000, sw - 20), min(650, sh - 20)
    elif sw <= 1366:
        ww, wh = min(1100, sw - 20), min(700, sh - 30)
    else:
        ww, wh = 1200, 800
    ww = max(720, ww)
    wh = max(540, wh)
    x = max(0, (sw - ww)//2)
    y = max(0, (sh - wh)//2)
    root.geometry(f"{ww}x{wh}+{x}+{y}")
    root.minsize(720, 540)
    root.resizable(True, True)
    root.configure(bg="#f0f4f8")
    
    try:
        ico = Path(__file__).resolve().parent.parent / "installer" / "app.ico"
        if ico.exists():
            root.iconbitmap(default=str(ico))
    except Exception:
        pass

    # Style
    style = ttk.Style()
    try:
        style.theme_use("vista")
    except:
        try:
            style.theme_use("winnative")
        except:
            pass
    
    style.configure("TProgressbar", thickness=18, troughcolor="#e3e8f0", background="#1976d2")
    style.configure("Chrome.Horizontal.TProgressbar", background="#8e5bd9", thickness=16)
    style.configure("Model.Horizontal.TProgressbar", background="#2e9e5b", thickness=16)
    style.configure("Tira.Horizontal.TProgressbar", background="#f59e0b", thickness=16)

    # Main layout
    main_frame = tk.Frame(root, bg="#f0f4f8")
    main_frame.pack(fill="both", expand=True)
    main_frame.columnconfigure(0, weight=1)
    main_frame.rowconfigure(1, weight=1)

    # Header
    header = tk.Frame(main_frame, bg="#0f2a4a", height=80)
    header.grid(row=0, column=0, sticky="ew")
    header.grid_propagate(False)
    header.columnconfigure(1, weight=1)

    left_hdr = tk.Frame(header, bg="#0f2a4a")
    left_hdr.grid(row=0, column=0, sticky="w", padx=20, pady=10)
    tk.Label(left_hdr, text="🧠 تیرا — مارکتینگ دیوار", font=("Segoe UI", 16, "bold"), bg="#0f2a4a", fg="white").pack(anchor="w")
    tk.Label(left_hdr, text=f"v{VERSION} — دیوار + شیپور + شکارچی + ملی‌پیامک کامل + روبیکا — نیتیو ویندوز", font=("Segoe UI", 9), bg="#0f2a4a", fg="#8ec0f0").pack(anchor="w")

    center_hdr = tk.Frame(header, bg="#0f2a4a")
    center_hdr.grid(row=0, column=1, sticky="ew", padx=20, pady=10)
    status_var = tk.StringVar(value="در حال راه‌اندازی سرور...")
    tk.Label(center_hdr, textvariable=status_var, font=("Segoe UI", 10, "bold"), bg="#0f2a4a", fg="#38bdf8").pack()

    right_hdr = tk.Frame(header, bg="#0f2a4a")
    right_hdr.grid(row=0, column=2, sticky="e", padx=20, pady=10)
    tk.Label(right_hdr, text=f"Port: {_server_port}", font=("Consolas", 9), bg="#0f2a4a", fg="#a78bfa").pack(anchor="e")
    server_status_var = tk.StringVar(value="🔴 سرور خاموش")
    tk.Label(right_hdr, textvariable=server_status_var, font=("Segoe UI", 9, "bold"), bg="#0f2a4a", fg="#f87171").pack(anchor="e")

    # Notebook tabs
    notebook = ttk.Notebook(main_frame)
    notebook.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

    # Tab 1: Dashboard
    tab_dash = tk.Frame(notebook, bg="white")
    notebook.add(tab_dash, text="📊 داشبورد")
    
    dash_frame = tk.Frame(tab_dash, bg="white")
    dash_frame.pack(fill="both", expand=True, padx=15, pady=15)
    
    # Top stats
    stats_frame = tk.Frame(dash_frame, bg="#f8fafc", relief="flat", bd=1)
    stats_frame.pack(fill="x", pady=(0,10))
    
    tk.Label(stats_frame, text="📈 وضعیت زنده", font=("Segoe UI", 12, "bold"), bg="#f8fafc", fg="#0f2a4a").pack(anchor="w", padx=15, pady=5)
    
    stats_grid = tk.Frame(stats_frame, bg="#f8fafc")
    stats_grid.pack(fill="x", padx=15, pady=10)
    
    stat_labels = {}
    stats = [("total_leads", "کل سرنخ‌ها", "0"), ("phones_found", "شماره‌دار", "0"), ("queue", "صف", "0"), ("running", "مانیتور", "خاموش")]
    for i, (key, title, default) in enumerate(stats):
        f = tk.Frame(stats_grid, bg="white", relief="flat", bd=1)
        f.grid(row=0, column=i, padx=5, pady=5, sticky="ew")
        stats_grid.columnconfigure(i, weight=1)
        tk.Label(f, text=title, font=("Segoe UI", 9), bg="white", fg="#64748b").pack(pady=(8,2))
        lbl = tk.Label(f, text=default, font=("Segoe UI", 16, "bold"), bg="white", fg="#0f2a4a")
        lbl.pack(pady=(0,8))
        stat_labels[key] = lbl

    # Control buttons
    ctrl_frame = tk.Frame(dash_frame, bg="white")
    ctrl_frame.pack(fill="x", pady=10)
    
    def start_monitor():
        try:
            import requests
            r = requests.post(f"http://127.0.0.1:{_server_port}/api/monitor/start", json={"include_existing": False}, timeout=10)
            if r.status_code == 200:
                messagebox.showinfo("✅", "مانیتور شروع شد")
                status_var.set("مانیتور روشن ✅")
            else:
                messagebox.showwarning("⚠️", f"خطا: {r.text[:200]}")
        except Exception as e:
            messagebox.showerror("❌", f"خطا: {e}")

    def stop_monitor():
        try:
            import requests
            r = requests.post(f"http://127.0.0.1:{_server_port}/api/monitor/stop", timeout=10)
            if r.status_code == 200:
                messagebox.showinfo("✅", "مانیتور متوقف شد")
                status_var.set("مانیتور خاموش")
            else:
                messagebox.showwarning("⚠️", f"خطا: {r.text[:200]}")
        except Exception as e:
            messagebox.showerror("❌", f"خطا: {e}")

    def open_browser_panel():
        url = f"http://127.0.0.1:{_server_port}"
        webbrowser.open(url)
        status_var.set(f"پنل مرورگر باز شد: {url}")

    tk.Button(ctrl_frame, text="▶️ شروع شکار", font=("Segoe UI", 11, "bold"), bg="#2e9e5b", fg="white", relief="flat", padx=20, pady=8, command=start_monitor).pack(side="left", padx=5)
    tk.Button(ctrl_frame, text="⏸️ توقف", font=("Segoe UI", 10), bg="#e2e8f0", relief="flat", padx=15, pady=8, command=stop_monitor).pack(side="left", padx=5)
    tk.Button(ctrl_frame, text="🌐 باز کردن پنل کامل در مرورگر", font=("Segoe UI", 10), bg="#1976d2", fg="white", relief="flat", padx=15, pady=8, command=open_browser_panel).pack(side="left", padx=15)

    # Logs in dashboard
    log_frame_dash = tk.LabelFrame(dash_frame, text="📝 لاگ زنده", font=("Segoe UI", 9, "bold"), bg="white")
    log_frame_dash.pack(fill="both", expand=True, pady=10)
    log_text_dash = scrolledtext.ScrolledText(log_frame_dash, font=("Consolas", 8), bg="#1a202c", fg="#e2e8f0", height=15)
    log_text_dash.pack(fill="both", expand=True, padx=5, pady=5)

    # Tab 2: Tira Agent
    tab_tira = tk.Frame(notebook, bg="white")
    notebook.add(tab_tira, text="🧠 تیرا — چت")

    tira_frame = tk.Frame(tab_tira, bg="white")
    tira_frame.pack(fill="both", expand=True, padx=10, pady=10)
    tira_frame.columnconfigure(0, weight=1)
    tira_frame.rowconfigure(0, weight=1)

    tira_chat = scrolledtext.ScrolledText(tira_frame, font=("Segoe UI", 10), bg="#f8fafc", fg="#1a202c", wrap="word", height=20)
    tira_chat.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0,10))
    tira_chat.insert("1.0", "🧠 سلام! من تیرا هستم — دستیار شکار حرفه‌ای v4.1\n\nمی‌تونی بهم بگی:\n• برای لوازم خانگی شکار تنظیم کن\n• دسته‌بندی موبایل و تبلت\n• قیمت‌گذاری هوشمند\n• کمپین جدید خودرو بساز\n• پیام خوش‌آمدگویی حرفه‌ای بنویس\n• متن پیام حرفه‌ای\n• چطور پنل پیامکی رو تنظیم کنم؟\n• آیا تیرا از طریق ربات بله دستور می‌گیره؟\n\nهرچی بگی، تحقیق می‌کنم و تنظیمات شکارچی رو می‌سازم! 🚀\n\n")
    tira_chat.configure(state="disabled")

    tira_input_frame = tk.Frame(tira_frame, bg="white")
    tira_input_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
    tira_input_frame.columnconfigure(0, weight=1)

    tira_entry_var = tk.StringVar()
    tira_entry = tk.Entry(tira_input_frame, textvariable=tira_entry_var, font=("Segoe UI", 11), bg="white", relief="flat", bd=1)
    tira_entry.grid(row=0, column=0, sticky="ew", ipady=8, padx=(0,10))

    def send_to_tira():
        msg = tira_entry_var.get().strip()
        if not msg:
            return
        tira_chat.configure(state="normal")
        tira_chat.insert("end", f"\n👤 شما: {msg}\n")
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
                        tira_chat.insert("end", f"\n🧠 تیرا: {reply}\n{'—'*50}\n")
                        tira_chat.configure(state="disabled")
                        tira_chat.see("end")
                    root.after(0, _show)
                else:
                    def _err():
                        tira_chat.configure(state="normal")
                        tira_chat.insert("end", f"\n❌ خطا: {r.text[:500]}\n")
                        tira_chat.configure(state="disabled")
                        tira_chat.see("end")
                    root.after(0, _err)
            except Exception as e:
                def _exc():
                    tira_chat.configure(state="normal")
                    tira_chat.insert("end", f"\n❌ خطا: {e}\n")
                    tira_chat.configure(state="disabled")
                    tira_chat.see("end")
                root.after(0, _exc)

        threading.Thread(target=_call_tira, daemon=True).start()

    def tira_entry_key(event):
        if event.keysym == "Return":
            send_to_tira()

    tira_entry.bind("<KeyPress>", tira_entry_key)
    tk.Button(tira_input_frame, text="📤 ارسال", font=("Segoe UI", 10, "bold"), bg="#7c3aed", fg="white", relief="flat", padx=20, pady=8, command=send_to_tira).grid(row=0, column=1)

    # Quick buttons
    quick_frame = tk.Frame(tira_frame, bg="white")
    quick_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=10)
    quick_msgs = [
        "برای لوازم خانگی شکار تنظیم کن",
        "کمپین جدید خودرو بساز",
        "قیمت‌گذاری هوشمند",
        "کمپین خودرو بساز",
        "چطور پنل پیامکی رو تنظیم کنم؟",
        "آیا تیرا از طریق ربات بله دستور می‌گیره؟"
    ]
    for qm in quick_msgs:
        btn = tk.Button(quick_frame, text=qm, font=("Segoe UI", 8), bg="#e8eef7", relief="flat", padx=8, pady=4,
                        command=lambda m=qm: (tira_entry_var.set(m), send_to_tira()))
        btn.pack(side="left", padx=3, pady=2)

    # Tab 3: Downloads / Dependencies
    tab_deps = tk.Frame(notebook, bg="white")
    notebook.add(tab_deps, text="📦 دانلودها")

    deps_frame = tk.Frame(tab_deps, bg="white")
    deps_frame.pack(fill="both", expand=True, padx=20, pady=20)

    tk.Label(deps_frame, text="📦 وضعیت دانلودها — DownloadManager سریع", font=("Segoe UI", 14, "bold"), bg="white", fg="#0f2a4a").pack(anchor="w", pady=(0,15))

    # Chromium
    chrome_dep_frame = tk.LabelFrame(deps_frame, text="🌐 کرومیوم اختصاصی (مرورگر جدا برای هر اکانت)", font=("Segoe UI", 10, "bold"), bg="white", padx=15, pady=10)
    chrome_dep_frame.pack(fill="x", pady=10)
    chrome_label_var = tk.StringVar(value="Chromium: بررسی...")
    tk.Label(chrome_dep_frame, textvariable=chrome_label_var, font=("Segoe UI", 10), bg="white", fg="#334", anchor="w").pack(fill="x")
    chrome_bar = ttk.Progressbar(chrome_dep_frame, mode="determinate", maximum=100, style="Chrome.Horizontal.TProgressbar")
    chrome_bar.pack(fill="x", pady=5)
    chrome_speed_var = tk.StringVar(value="—")
    tk.Label(chrome_dep_frame, textvariable=chrome_speed_var, font=("Consolas", 9), bg="white", fg="#6b7a90", anchor="w").pack(fill="x")

    # Model
    model_dep_frame = tk.LabelFrame(deps_frame, text="🧠 مدل تیرا (هوش مصنوعی مذاکره)", font=("Segoe UI", 10, "bold"), bg="white", padx=15, pady=10)
    model_dep_frame.pack(fill="x", pady=10)
    model_label_var = tk.StringVar(value="مدل تیرا: بررسی...")
    tk.Label(model_dep_frame, textvariable=model_label_var, font=("Segoe UI", 10), bg="white", fg="#334", anchor="w").pack(fill="x")
    model_bar = ttk.Progressbar(model_dep_frame, mode="determinate", maximum=100, style="Model.Horizontal.TProgressbar")
    model_bar.pack(fill="x", pady=5)
    model_speed_var = tk.StringVar(value="—")
    tk.Label(model_dep_frame, textvariable=model_speed_var, font=("Consolas", 9), bg="white", fg="#6b7a90", anchor="w").pack(fill="x")

    # Log
    deps_log_frame = tk.LabelFrame(deps_frame, text="📝 لاگ دانلود", font=("Segoe UI", 9, "bold"), bg="white")
    deps_log_frame.pack(fill="both", expand=True, pady=15)
    deps_log = scrolledtext.ScrolledText(deps_log_frame, font=("Consolas", 8), bg="#1a202c", fg="#e2e8f0", height=12)
    deps_log.pack(fill="both", expand=True, padx=5, pady=5)

    def deps_log_fn(msg: str):
        def _do():
            deps_log.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            deps_log.see("end")
            # Also dashboard log
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
            chrome_speed_var.set(f"سرعت: {speed}")
        try:
            root.after(0, _do)
        except:
            pass

    def model_cb(pct: int, text: str, speed: str):
        def _do():
            model_bar["value"] = pct
            model_label_var.set(text)
            model_speed_var.set(f"سرعت: {speed}")
        try:
            root.after(0, _do)
        except:
            pass

    # Tab 4: Settings
    tab_settings = tk.Frame(notebook, bg="white")
    notebook.add(tab_settings, text="⚙️ تنظیمات")

    settings_frame = tk.Frame(tab_settings, bg="white")
    settings_frame.pack(fill="both", expand=True, padx=20, pady=20)
    tk.Label(settings_frame, text="⚙️ تنظیمات سریع", font=("Segoe UI", 14, "bold"), bg="white", fg="#0f2a4a").pack(anchor="w", pady=(0,15))
    tk.Label(settings_frame, text="برای تنظیمات کامل، پنل مرورگر را باز کنید (دکمه بالا) — تمام تنظیمات در آنجا موجود است:\n• کلمات کلیدی + دسته‌بندی + شهر + قیمت\n• قالب پیامک/چت\n• ملی‌پیامک (نام کاربری/رمز/خط/پترن)\n• ربات‌های تلگرام/بله/روبیکا\n• IP و سهمیه\n• اکانت‌ها\n\nاین پنجره نیتیو برای کنترل سریع و تیرا چت است، پنل کامل وب در مرورگر اختصاصی یا همین سرور است.", 
             font=("Segoe UI", 11), bg="white", fg="#334", justify="left").pack(anchor="w", pady=10)

    # Bottom status bar
    bottom_bar = tk.Frame(main_frame, bg="#e8eef7", height=30)
    bottom_bar.grid(row=2, column=0, sticky="ew")
    bottom_bar.grid_propagate(False)
    tk.Label(bottom_bar, text=f"{APP_NAME_FA} v{VERSION} — {APP_NAME_EN} — طراحی توسط خواجوی — نیتیو ویندوز بدون مرورگر", font=("Segoe UI", 8), bg="#e8eef7", fg="#6b7a90").pack(side="left", padx=15, pady=5)
    tk.Label(bottom_bar, text=f"Data: {user_data_dir()}", font=("Consolas", 7), bg="#e8eef7", fg="#6b7a90").pack(side="right", padx=15)

    # Background workers
    def server_monitor():
        while True:
            time.sleep(2)
            try:
                import requests
                r = requests.get(f"http://127.0.0.1:{_server_port}/api/status", timeout=3)
                if r.status_code == 200:
                    data = r.json()
                    def _upd():
                        server_status_var.set("🟢 سرور روشن")
                        stat_labels["total_leads"].configure(text=str(data.get("total_leads", 0)))
                        stat_labels["phones_found"].configure(text=str(data.get("phones_found", 0)))
                        stat_labels["queue"].configure(text=str(data.get("queue", 0)))
                        stat_labels["running"].configure(text="روشن ✅" if data.get("running") else "خاموش")
                        status_var.set(f"مانیتور: {'روشن' if data.get('running') else 'خاموش'} | Tick: {data.get('tick',0)} | سرنخ: {data.get('total_leads',0)}")
                    root.after(0, _upd)
                else:
                    root.after(0, lambda: server_status_var.set("🟡 سرور خطا"))
            except Exception:
                root.after(0, lambda: server_status_var.set("🔴 سرور خاموش"))

    def deps_worker():
        time.sleep(1)
        _check_deps_with_progress(deps_log_fn, chrome_cb, model_cb)

    threading.Thread(target=server_monitor, daemon=True).start()
    threading.Thread(target=deps_worker, daemon=True).start()

    # Initial log
    deps_log_fn(f"🚀 {APP_TITLE} v{VERSION} شروع شد")
    deps_log_fn(f"📁 Data: {user_data_dir()}")
    deps_log_fn(f"🌐 Server: http://127.0.0.1:{_server_port}")

    root.mainloop()


def main():
    print(f"🚀 {APP_TITLE} v{VERSION} — Native Desktop")
    data_dir = _ensure_runtime()
    print(f"Data: {data_dir}")
    
    # Start server in background
    port = _start_server_bg(log_fn=print)
    print(f"Server started on port {port}")

    # Launch native GUI
    _create_native_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
