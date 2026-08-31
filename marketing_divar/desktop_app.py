# -*- coding: utf-8 -*-
"""🧠 تیرا — دسکتاپ مستقل بدون مرورگر (تمیز و مرتب)

- یک پنجره اختصاصی مثل برنامه‌های نصب شده
- با pywebview (WebView2 در ویندوز) → native window، نه تب مرورگر
- fallback: tkinter splash زیبا + دکمه باز کردن پنل در Chromium اختصاصی
- چک خودکار مدل و Chromium با DownloadManager
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from .paths import apply_runtime_paths, user_data_dir
from .brand import APP_NAME_EN, APP_NAME_FA, PORT

APP_TITLE = f"🧠 تیرا - دستیار شکار حرفه‌ای | {APP_NAME_FA}"
VERSION = "3.4.3-tira-responsive"


def _ensure_runtime() -> Path:
    dest = apply_runtime_paths()
    for sub in ("accounts", "logs", "app-chromium", "nlu-model", "data"):
        (dest / sub).mkdir(parents=True, exist_ok=True)
    # DB
    try:
        from .db import connect, init_db
        db_path = dest / "divar_leads.db"
        if not db_path.exists():
            con = connect(str(db_path))
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
    # Firewall
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


def _start_server() -> tuple[object, int]:
    from .web.server import app, start_background
    import uvicorn

    host = "127.0.0.1"
    port = PORT

    # پورت آزاد
    import socket
    def _free(p: int) -> bool:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((host, p))
            s.close()
            return True
        except OSError:
            return False

    for _ in range(5):
        if _free(port):
            break
        port += 1

    start_background()

    def _run():
        try:
            uvicorn.run(app, host=host, port=port, log_level="warning")
        except Exception:
            pass

    th = threading.Thread(target=_run, daemon=True)
    th.start()

    for _ in range(40):
        time.sleep(0.5)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect((host, port))
            s.close()
            break
        except Exception:
            continue
    return th, port


def _check_deps(log_fn: Optional[Callable[[str], None]] = None):
    def log(m: str):
        if log_fn:
            log_fn(m)
        else:
            print(m)

    # Chromium
    try:
        from .app_chromium import is_ready, status, start_install_async
        if not is_ready():
            log("📥 Chromium نصب نیست — دانلود...")
            start_install_async()
            for _ in range(15):
                time.sleep(1)
                st = status()
                if st.get("installed"):
                    log("✅ Chromium آماده")
                    break
        else:
            log("✅ Chromium آماده")
    except Exception as e:
        log(f"Chromium: {e}")

    # Model
    try:
        from .nlu_model import is_ready, status, start_install_async
        if not is_ready():
            log("📥 مدل تیرا نصب نیست — دانلود...")
            start_install_async()
            for _ in range(15):
                time.sleep(1)
                st = status()
                if st.get("ready") or st.get("installed"):
                    log(f"✅ مدل تیرا آماده")
                    break
        else:
            st = status()
            log(f"✅ مدل تیرا آماده: {st.get('backend')}")
    except Exception as e:
        log(f"Model: {e}")


def _open_pywebview(url: str) -> bool:
    try:
        import webview
    except ImportError:
        return False

    try:
        print(f"🖥️ Opening native Tira window: {url}")
        window = webview.create_window(
            title=APP_TITLE,
            url=url,
            width=1280,
            height=860,
            min_size=(1024, 640),
            background_color="#0f172a",
            text_select=True,
        )
        webview.start(debug=False, http_server=False)
        return True
    except Exception as e:
        print(f"pywebview failed: {e}")
        return False


def _open_tkinter(url: str, port: int):
    try:
        import tkinter as tk
        from tkinter import ttk
        import webbrowser
    except Exception:
        webbrowser.open(url)
        return

    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("600x620")
    root.minsize(520, 480)
    root.resizable(True, True)
    root.configure(bg="#0f172a")
    try:
        root.update_idletasks()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        x = (sw - 600) // 2
        y = (sh - 620) // 2
        root.geometry(f"600x620+{x}+{y}")
    except Exception:
        pass
    try:
        ico = Path(__file__).resolve().parent.parent / "installer" / "app.ico"
        if ico.exists():
            root.iconbitmap(default=str(ico))
    except Exception:
        pass

    main = tk.Frame(root, bg="#0f172a")
    main.pack(fill="both", expand=True, padx=0, pady=0)
    main.columnconfigure(0, weight=1)
    main.rowconfigure(3, weight=1)

    # header - grid row 0
    hdr = tk.Frame(main, bg="#0f172a")
    hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))
    hdr.columnconfigure(0, weight=1)
    tk.Label(hdr, text="🧠 تیرا", font=("Segoe UI", 20, "bold"), fg="#a78bfa", bg="#0f172a", anchor="w").pack(anchor="w")
    tk.Label(hdr, text="دستیار شکار حرفه‌ای — نسخه دسکتاپ مستقل", font=("Segoe UI", 10), fg="#e2e8f0", bg="#0f172a", anchor="w").pack(anchor="w")
    tk.Label(hdr, text=f"{APP_NAME_FA} — بدون نیاز به مرورگر", font=("Segoe UI", 8),
             fg="#94a3b8", bg="#0f172a", anchor="w").pack(anchor="w")

    status_var = tk.StringVar(value="در حال راه‌اندازی...")
    tk.Label(main, textvariable=status_var, font=("Segoe UI", 9, "bold"), fg="#38bdf8", bg="#0f172a", anchor="w").grid(row=1, column=0, sticky="ew", padx=16, pady=2)

    prog_frame = tk.Frame(main, bg="#0f172a")
    prog_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=2)
    prog_frame.columnconfigure(0, weight=1)

    lbl_chrome = tk.Label(prog_frame, text="Chromium: بررسی...", font=("Segoe UI", 8), fg="#cbd5e1", bg="#0f172a", anchor="w")
    lbl_chrome.pack(fill="x")
    bar_chrome = ttk.Progressbar(prog_frame, mode="determinate", maximum=100)
    bar_chrome.pack(fill="x", pady=1)

    lbl_nlu = tk.Label(prog_frame, text="مدل تیرا: بررسی...", font=("Segoe UI", 8), fg="#cbd5e1", bg="#0f172a", anchor="w")
    lbl_nlu.pack(fill="x", pady=(4, 0))
    bar_nlu = ttk.Progressbar(prog_frame, mode="determinate", maximum=100)
    bar_nlu.pack(fill="x", pady=1)

    # log expandable
    log_frame = tk.Frame(main, bg="#0f172a")
    log_frame.grid(row=3, column=0, sticky="nsew", padx=16, pady=6)
    log_frame.columnconfigure(0, weight=1)
    log_frame.rowconfigure(0, weight=1)

    logbox = tk.Text(log_frame, font=("Consolas", 8), bg="#1e293b", fg="#e2e8f0", relief="flat", wrap="word")
    logbox.grid(row=0, column=0, sticky="nsew")
    sb = ttk.Scrollbar(log_frame, orient="vertical", command=logbox.yview)
    sb.grid(row=0, column=1, sticky="ns")
    logbox.configure(yscrollcommand=sb.set, state="disabled")

    def log(msg: str):
        def _do():
            logbox.configure(state="normal")
            logbox.insert("end", msg + "\n")
            logbox.see("end")
            logbox.configure(state="disabled")
            status_var.set(msg[:90])
        try:
            root.after(0, _do)
        except Exception:
            print(msg)

    def upd_chrome(pct: int, txt: str):
        def _do():
            bar_chrome["value"] = pct
            lbl_chrome.configure(text=txt)
        try:
            root.after(0, _do)
        except Exception:
            pass

    def upd_nlu(pct: int, txt: str):
        def _do():
            bar_nlu["value"] = pct
            lbl_nlu.configure(text=txt)
        try:
            root.after(0, _do)
        except Exception:
            pass

    def open_panel():
        try:
            from .app_chromium import open_in_app_chromium
            res = open_in_app_chromium(url)
            if res.get("ok"):
                log("✅ پنل در Chromium اختصاصی باز شد")
                return
        except Exception:
            pass
        webbrowser.open(url)
        log(f"🌐 {url}")

    btn_frame = tk.Frame(main, bg="#0f172a")
    btn_frame.grid(row=4, column=0, sticky="ew", padx=16, pady=8)
    btn_frame.columnconfigure(0, weight=1)

    tk.Button(btn_frame, text="🚀 باز کردن پنل تیرا", font=("Segoe UI", 10, "bold"),
              bg="#7c3aed", fg="white", activebackground="#6d28d9", relief="flat",
              padx=10, pady=8, command=open_panel, cursor="hand2").grid(row=0, column=0, sticky="ew", padx=(0, 6))
    tk.Button(btn_frame, text="خروج", font=("Segoe UI", 9), bg="#334155", fg="white",
              relief="flat", padx=10, pady=8, command=root.destroy).grid(row=0, column=1)

    tk.Label(main, text=f"📍 {url} | 📱 موبایل همین Wi-Fi: http://<IP>:{port}",
             font=("Segoe UI", 7), fg="#64748b", bg="#0f172a", wraplength=560).grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 8))

    def worker():
        try:
            log(f"📁 {user_data_dir()}")
            _check_deps(log)
            for _ in range(60):
                time.sleep(1)
                try:
                    from .app_chromium import status as cs
                    st = cs()
                    pct = int(st.get("percent") or (100 if st.get("installed") else 0))
                    upd_chrome(pct, f"Chromium: {st.get('note') or 'آماده'} {pct}%")
                except Exception:
                    pass
                try:
                    from .nlu_model import status as ns
                    st = ns()
                    pct = int(st.get("percent") or (100 if st.get("ready") else 0))
                    upd_nlu(pct, f"مدل تیرا: {st.get('note') or st.get('backend') or ''} {pct}%")
                except Exception:
                    pass
            log("✅ آماده — دکمه را بزن")
            status_var.set("آماده ✅")
            root.after(1500, open_panel)
        except Exception as e:
            log(f"❌ {e}")

    threading.Thread(target=worker, daemon=True).start()
    root.mainloop()


def main():
    print(f"🚀 {APP_TITLE} v{VERSION} — Desktop")
    data_dir = _ensure_runtime()
    print(f"Data: {data_dir}")
    th, port = _start_server()
    url = f"http://127.0.0.1:{port}"
    print(f"Server: {url}")

    # اول pywebview
    try:
        if _open_pywebview(url):
            return 0
    except Exception as e:
        print(f"pywebview error: {e}")

    print("Fallback to tkinter")
    _open_tkinter(url, port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
