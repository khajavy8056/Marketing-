# -*- coding: utf-8 -*-
"""🧠 تیرا — دسکتاپ مستقل بدون مرورگر

پنل اصلی به صورت پنجره native (pywebview) باز می‌شود، نه تب مرورگر.
- اگر pywebview نصب باشد: پنجره مستقل با WebView2 (ویندوز) / WebKit (مک) / WebKitGTK (لینوکس)
- اگر نباشد: fallback به Chromium اختصاصی + tkinter splash زیبا
- هنگام اجرا: چک خودکار مدل Qwen و Chromium با دانلود منیجر استاندارد
- اتصالات سیستم: پوشه داده، دیتابیس، فایروال، میانبر، تنظیمات

اجرا: python -m marketing_divar.desktop_app
یا:   python main.py --desktop
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

APP_TITLE = f"🧠 تیرا - دستیار شکار حرفه‌ای | {APP_NAME_FA}"
AI_NAME = "تیرا"

def _ensure_runtime() -> Path:
    """پوشه داده پایدار + اتصالات لازم سیستم"""
    dest = apply_runtime_paths()
    # پوشه‌های لازم
    for sub in ("accounts", "logs", "app-chromium", "nlu-model", "data"):
        (dest / sub).mkdir(parents=True, exist_ok=True)
    # دیتابیس خالی اگر نیست
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
    # فایروال (فقط ویندوز، بی‌صدا)
    try:
        if sys.platform == "win32":
            import subprocess
            cmd = [
                "netsh", "advfirewall", "firewall", "add", "rule",
                f"name={APP_NAME_EN}", "dir=in", "action=allow",
                "protocol=TCP", f"localport={PORT}",
            ]
            subprocess.run(cmd, capture_output=True, timeout=10)
    except Exception:
        pass
    return dest

def _start_server() -> tuple[object, int]:
    """FastAPI را در thread جدا بالا می‌آورد"""
    from .web.server import app, start_background
    import uvicorn

    host = "127.0.0.1"
    port = PORT

    # چک پورت آزاد
    def _is_free(p: int) -> bool:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((host, p))
            s.close()
            return True
        except OSError:
            return False

    # اگر پورت اشغال است، سعی کن 8643, 8644 ...
    for _ in range(5):
        if _is_free(port):
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
    # صبر تا بالا بیاید
    for _ in range(30):
        time.sleep(0.5)
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect((host, port))
            s.close()
            break
        except Exception:
            continue
    return th, port

def _check_and_download_dependencies(log_fn: Optional[Callable[[str], None]] = None):
    """چک مدل و کرومیوم — اگر نیست با دانلود منیجر استاندارد دانلود کن"""
    def log(msg: str):
        if log_fn:
            log_fn(msg)
        else:
            print(msg)

    # Chromium
    try:
        from .app_chromium import is_ready as chrome_ready, status as chrome_status
        if not chrome_ready():
            log("📥 Chromium اختصاصی نصب نیست — دانلود با دانلود منیجر...")
            from .app_chromium import start_install_async
            start_install_async()
            # صبر کوتاه، بقیه در پس‌زمینه ادامه می‌یابد و پنل خودش نشان می‌دهد
            for _ in range(10):
                time.sleep(1)
                st = chrome_status()
                if st.get("installed"):
                    log("✅ Chromium آماده شد")
                    break
                if st.get("percent"):
                    log(f"Chromium {st.get('percent')}%")
        else:
            log("✅ Chromium آماده")
    except Exception as e:
        log(f"⚠️ Chromium check: {e}")

    # NLU Model
    try:
        from .nlu_model import is_ready as nlu_ready, status as nlu_status
        if not nlu_ready():
            log("📥 مدل تیرا (Qwen) نصب نیست — دانلود با دانلود منیجر...")
            from .nlu_model import start_install_async as nlu_start
            nlu_start()
            for _ in range(10):
                time.sleep(1)
                st = nlu_status()
                if st.get("ready") or st.get("installed"):
                    log(f"✅ مدل تیرا آماده — {st.get('backend')}")
                    break
                if st.get("percent"):
                    log(f"مدل تیرا {st.get('percent')}%")
        else:
            st = nlu_status()
            log(f"✅ مدل تیرا آماده — {st.get('backend')}")
    except Exception as e:
        log(f"⚠️ NLU check: {e}")

def _open_with_pywebview(url: str, port: int) -> bool:
    """سعی کن با pywebview پنجره native باز کنی"""
    try:
        import webview  # type: ignore
    except ImportError:
        return False

    # تنظیمات پنجره زیبا
    try:
        # آیکون
        icon_path = None
        for cand in [
            Path(__file__).resolve().parent.parent / "installer" / "app.ico",
            user_data_dir() / "app.ico",
            Path(__file__).resolve().parent / "web" / "static" / "logo.png",
        ]:
            if cand.exists():
                icon_path = str(cand)
                break

        window = webview.create_window(
            title=APP_TITLE,
            url=url,
            width=1280,
            height=860,
            min_size=(1024, 640),
            background_color="#0f172a",
            text_select=True,
        )

        # استایل اضافی برای ویندوز
        # webview.start با GUI loop
        print(f"🖥️ پنجره مستقل تیرا باز می‌شود: {url}")
        webview.start(
            debug=False,
            http_server=False,
            # برای ویندوز: از Edge WebView2 استفاده کن (native، نه مرورگر)
            # private_mode=False تا کوکی‌ها بمانند
        )
        return True
    except Exception as e:
        print(f"pywebview failed: {e}")
        return False

def _open_with_tkinter_splash(url: str, port: int):
    """Fallback زیبا با tkinter — اسپلش + دکمه باز کردن پنل"""
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        # آخرین fallback: مرورگر سیستمی
        webbrowser.open(url)
        return

    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("520x620")
    root.resizable(False, False)
    # پس‌زمینه گرادینت شبیه‌سازی با رنگ تیره
    root.configure(bg="#0f172a")

    # تلاش برای آیکون
    try:
        ico = Path(__file__).resolve().parent.parent / "installer" / "app.ico"
        if ico.exists():
            root.iconbitmap(default=str(ico))
    except Exception:
        pass

    # فریم اصلی
    main = tk.Frame(root, bg="#0f172a")
    main.pack(fill="both", expand=True, padx=24, pady=24)

    # لوگو / عنوان
    title_lbl = tk.Label(
        main,
        text="🧠 تیرا",
        font=("Segoe UI", 32, "bold"),
        fg="#a78bfa",
        bg="#0f172a",
    )
    title_lbl.pack(pady=(20, 4))

    subtitle = tk.Label(
        main,
        text="دستیار شکار حرفه‌ای تو! 🎯",
        font=("Segoe UI", 14),
        fg="#e2e8f0",
        bg="#0f172a",
    )
    subtitle.pack()

    desc = tk.Label(
        main,
        text=f"{APP_NAME_FA} — نسخه دسکتاپ مستقل\nبدون نیاز به مرورگر، پنجره اختصاصی",
        font=("Segoe UI", 10),
        fg="#94a3b8",
        bg="#0f172a",
        justify="center",
    )
    desc.pack(pady=(12, 20))

    # وضعیت
    status_var = tk.StringVar(value="در حال راه‌اندازی سرور...")
    status_lbl = tk.Label(
        main,
        textvariable=status_var,
        font=("Segoe UI", 10),
        fg="#38bdf8",
        bg="#0f172a",
        wraplength=460,
        justify="center",
    )
    status_lbl.pack(pady=8)

    # پروگرس بارها
    bar_chrome = ttk.Progressbar(main, length=440, mode="determinate", maximum=100)
    bar_chrome.pack(pady=4)
    lbl_chrome = tk.Label(main, text="Chromium: بررسی...", font=("Segoe UI", 9), fg="#cbd5e1", bg="#0f172a")
    lbl_chrome.pack()

    bar_nlu = ttk.Progressbar(main, length=440, mode="determinate", maximum=100)
    bar_nlu.pack(pady=4)
    lbl_nlu = tk.Label(main, text="مدل تیرا: بررسی...", font=("Segoe UI", 9), fg="#cbd5e1", bg="#0f172a")
    lbl_nlu.pack()

    # لاگ باکس
    logbox = tk.Text(main, height=10, font=("Consolas", 8), bg="#1e293b", fg="#e2e8f0", relief="flat")
    logbox.pack(fill="both", expand=True, pady=12)
    logbox.configure(state="disabled")

    def log(msg: str):
        def _do():
            logbox.configure(state="normal")
            logbox.insert("end", msg + "\n")
            logbox.see("end")
            logbox.configure(state="disabled")
            status_var.set(msg[:80])
        root.after(0, _do)

    def update_chrome(pct: int, txt: str):
        def _do():
            bar_chrome["value"] = pct
            lbl_chrome.configure(text=txt)
        root.after(0, _do)

    def update_nlu(pct: int, txt: str):
        def _do():
            bar_nlu["value"] = pct
            lbl_nlu.configure(text=txt)
        root.after(0, _do)

    # دکمه‌ها
    btn_frame = tk.Frame(main, bg="#0f172a")
    btn_frame.pack(fill="x", pady=12)

    def open_panel():
        # اول سعی کن با Chromium اختصاصی باز کنی (پنجره جدا، نه Edge)
        try:
            from .app_chromium import open_in_app_chromium
            res = open_in_app_chromium(url)
            if res.get("ok"):
                log("✅ پنل در Chromium اختصاصی باز شد")
                return
        except Exception:
            pass
        # fallback مرورگر
        webbrowser.open(url)
        log(f"🌐 پنل در مرورگر باز شد: {url}")

    def open_desktop():
        open_panel()

    btn_open = tk.Button(
        btn_frame,
        text="🚀 باز کردن پنل تیرا",
        font=("Segoe UI", 11, "bold"),
        bg="#7c3aed",
        fg="white",
        activebackground="#6d28d9",
        relief="flat",
        padx=20,
        pady=10,
        command=open_desktop,
        cursor="hand2",
    )
    btn_open.pack(side="left", expand=True, fill="x", padx=(0, 6))

    btn_close = tk.Button(
        btn_frame,
        text="خروج",
        font=("Segoe UI", 10),
        bg="#334155",
        fg="white",
        relief="flat",
        padx=12,
        pady=10,
        command=root.destroy,
    )
    btn_close.pack(side="right")

    # اطلاعات پایین
    info = tk.Label(
        main,
        text=f"📍 {url}\n📱 موبایل در همین Wi-Fi: http://<IP-این-سیستم>:{port}\n\n💡 پروفایل‌ها (دیوار/شیپور/رینگ) در پنجره Chromium جدا باز می‌شوند",
        font=("Segoe UI", 8),
        fg="#64748b",
        bg="#0f172a",
        justify="center",
    )
    info.pack(pady=(8, 0))

    # شروع چک‌ها در thread جدا
    def worker():
        try:
            log(f"📁 پوشه داده: {user_data_dir()}")
            # چک وابستگی‌ها
            _check_and_download_dependencies(log)

            # آپدیت پروگرس از status واقعی
            for _ in range(60):
                time.sleep(1)
                try:
                    from .app_chromium import status as cs
                    st = cs()
                    pct = int(st.get("percent") or (100 if st.get("installed") else 0))
                    note = st.get("note") or ("آماده" if st.get("installed") else "در انتظار")
                    update_chrome(pct, f"Chromium: {note} {pct}%")
                except Exception:
                    pass
                try:
                    from .nlu_model import status as ns
                    st = ns()
                    pct = int(st.get("percent") or (100 if st.get("ready") else 0))
                    note = st.get("note") or st.get("backend") or ""
                    update_nlu(pct, f"مدل تیرا: {note} {pct}%")
                except Exception:
                    pass

            log("✅ همه چیز آماده — دکمه باز کردن را بزن")
            status_var.set("آماده ✅ — پنل را باز کن")
            # خودکار باز کن بعد از 1.5 ثانیه
            root.after(1500, open_panel)
        except Exception as e:
            log(f"❌ خطا: {e}")

    threading.Thread(target=worker, daemon=True).start()

    root.mainloop()

def main():
    print(f"🚀 {APP_TITLE} — Desktop")
    data_dir = _ensure_runtime()
    print(f"Data: {data_dir}")

    # سرور را بالا بیار
    print("Starting server...")
    th, port = _start_server()
    url = f"http://127.0.0.1:{port}"
    print(f"Server at {url}")

    # اول سعی کن pywebview
    try:
        # اگر pywebview نصب نیست، نصب کن؟ نه، fallback
        if _open_with_pywebview(url, port):
            return 0
    except Exception as e:
        print(f"pywebview not available: {e}")

    # fallback tkinter splash + chromium
    print("Fallback to tkinter + app-chromium")
    _open_with_tkinter_splash(url, port)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
