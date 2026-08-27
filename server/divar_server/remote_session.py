# -*- coding: utf-8 -*-
"""نشست ریموت پروفایل Chromium روی سرور لینوکس.

طبق سند «نقشه-راه-پروفایل-ریموت-سرور»:

  مرورگر اپراتور ──https──▶ Nginx ──▶ برنامه (احراز هویت) ──ws──▶ websockify
        ──▶ x11vnc ──▶ Xvfb :N ──▶ Chromium headful با user_data_dir همان اکانت

- فقط «دیدن و کنترل از راه دور» یک مرورگر واقعی؛ **هیچ حل خودکار کپچایی ندارد**.
- حالت پیش‌فرض بسته: هیچ Xvfb/x11vnc/Chromium اجرا نیست، فقط پوشهٔ پروفایل
  روی دیسک باقی می‌ماند.
- هر نشست: یک شمارهٔ نمایش (:100..:199) + یک پورت VNC + یک پورت websockify.
- x11vnc / websockify فقط روی 127.0.0.1 بایند می‌شوند (هیچ پورت عمومی باز نمی‌شود).
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None

DISPLAY_MIN = 100
DISPLAY_MAX = 199
VNC_PORT_BASE = 5900
WS_PORT_BASE = 6900
IDLE_TIMEOUT_SEC = 600          # ۱۰ دقیقه بدون تعامل → بسته خودکار
MAX_SESSIONS = 100
HOME_URL = "https://divar.ir/user"

_LIVE: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()

_FAKE = os.environ.get("DIVAR_SERVER_NO_VNC", "0") == "1"   # برای تست بدون X


def _which(*names: str) -> Optional[str]:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def _free_port(start: int, span: int = 200) -> int:
    for p in range(start, start + span):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", p))
            s.close()
            return p
        except OSError:
            try:
                s.close()
            except Exception:
                pass
    raise RuntimeError("پورت آزاد پیدا نشد")


def _alloc_display() -> int:
    used = {int(v["display"].lstrip(":")) for v in _LIVE.values() if v.get("display")}
    for d in range(DISPLAY_MIN, DISPLAY_MAX + 1):
        if d not in used:
            return d
    raise RuntimeError("سقف نشست‌های هم‌زمان (۱۰۰) پر شد")


def _check_binaries() -> None:
    if _FAKE:
        return
    for names, label in (
        (("Xvfb",), "Xvfb"),
        (("x11vnc",), "x11vnc"),
        (("websockify",), "websockify"),
    ):
        if not _which(*names):
            raise RuntimeError(
                f"ابزار «{label}» روی سرور نصب نیست — نصب‌کننده را دوباره اجرا کنید "
                f"(apt install {' '.join(names)})")


def _chrome_executable() -> str:
    """Chromium مورد استفادهٔ Playwright (یا مسیر صریح از متغیر محیطی)."""
    override = os.environ.get("DIVAR_SERVER_CHROMIUM")
    if override:
        return override
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return p.chromium.executable_path
    except Exception as e:
        raise RuntimeError("Chromium پیدا نشد — «playwright install chromium» را اجرا کنید: %s" % e)


def _chromium_dir(accounts_dir: str, name: str) -> Path:
    from marketing_divar.chromium_profile import chromium_dir
    return Path(chromium_dir(accounts_dir, name))


# ------------------------------------------------------------------- API --
def status(name: Optional[str] = None) -> Dict[str, Any]:
    with _LOCK:
        if name:
            return {"open": name in _LIVE, "session": _sanitize(_LIVE.get(name))}
        return {"open_count": len(_LIVE),
                "sessions": {k: _sanitize(v) for k, v in _LIVE.items()}}


def _sanitize(v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not v:
        return None
    return {
        "account": v.get("account"),
        "display": v.get("display"),
        "vnc_port": v.get("vnc_port"),
        "ws_port": v.get("ws_port"),
        "started_at": v.get("started_at"),
        "last_activity": v.get("last_activity"),
        "idle_sec": round(time.time() - float(v.get("last_activity", time.time())), 1),
    }


def touch(name: str) -> None:
    with _LOCK:
        if name in _LIVE:
            _LIVE[name]["last_activity"] = time.time()


def open_remote(accounts_dir: str, name: str) -> Dict[str, Any]:
    """باز کردن نشست زندهٔ همان پروفایل اکانت (لاگین یا حل کپچا)."""
    name = (name or "").strip()
    if not name:
        return {"ok": False, "message": "نام اکانت خالی است"}
    with _LOCK:
        if name in _LIVE:
            s = _LIVE[name]
            s["last_activity"] = time.time()
            return {"ok": True, "already_open": True, **_sanitize(s)}
        if len(_LIVE) >= MAX_SESSIONS:
            return {"ok": False, "message": "سقف نشست‌های هم‌زمان پر است"}
    _check_binaries()
    display = _alloc_display()
    vnc_port = _free_port(VNC_PORT_BASE)
    ws_port = _free_port(WS_PORT_BASE)
    prof = _chromium_dir(accounts_dir, name)
    prof.mkdir(parents=True, exist_ok=True)

    if _FAKE:
        with _LOCK:
            _LIVE[name] = {
                "account": name, "display": f":{display}",
                "vnc_port": vnc_port, "ws_port": ws_port,
                "started_at": time.time(), "last_activity": time.time(),
                "procs": [], "context": None, "fake": True,
            }
        return {"ok": True, **_sanitize(_LIVE[name])}

    try:
        procs: List[subprocess.Popen] = []
        xvfb = subprocess.Popen(
            ["Xvfb", f":{display}", "-screen", "0", "1280x900x24"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(xvfb)
        # صبر تا Xvfb آماده شود
        for _ in range(40):
            if _display_ready(display):
                break
            time.sleep(0.1)
        x11vnc = subprocess.Popen(
            ["x11vnc", "-display", f":{display}", "-rfbport", str(vnc_port),
             "-localhost", "-nopw", "-shared", "-forever"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(x11vnc)
        novnc_web = _novnc_web_dir()
        ws = subprocess.Popen(
            ["websockify", str(ws_port), f"127.0.0.1:{vnc_port}",
             f"--web={novnc_web}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(ws)
        time.sleep(0.4)

        context = _launch_browser(prof, display)
        with _LOCK:
            _LIVE[name] = {
                "account": name, "display": f":{display}",
                "vnc_port": vnc_port, "ws_port": ws_port,
                "started_at": time.time(), "last_activity": time.time(),
                "procs": procs, "context": context,
            }
        return {"ok": True, **_sanitize(_LIVE[name])}
    except Exception as e:
        for p in procs:
            _kill(p)
        raise RuntimeError("باز کردن نشست ریموت ناموفق بود: %s" % e)


def _display_ready(display: int) -> bool:
    try:
        s = socket.create_connection(("127.0.0.1", VNC_PORT_BASE + (display - DISPLAY_MIN)), 0.3)
        s.close()
        return True
    except OSError:
        return False


def _novnc_web_dir() -> str:
    override = os.environ.get("DIVAR_NOVNC_DIR")
    if override and Path(override).exists():
        return override
    for cand in ("/opt/divar-server/novnc", "/opt/divar-server/noVNC"):
        if Path(cand).exists():
            return cand
    raise RuntimeError("noVNC پیدا نشد — نصب‌کننده را اجرا کنید (DIVAR_NOVNC_DIR)")


def _launch_browser(prof: Path, display: int) -> Any:
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    env = dict(os.environ)
    env["DISPLAY"] = f":{display}"
    context = p.chromium.launch_persistent_context(
        user_data_dir=str(prof),
        headless=False,
        executable_path=_chrome_executable(),
        viewport={"width": 1240, "height": 860},
        locale="fa-IR",
        timezone_id="Asia/Tehran",
        env=env,
        args=["--disable-blink-features=AutomationControlled", "--no-first-run"],
    )
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(HOME_URL, wait_until="domcontentloaded")
    return context


def close_remote(name: str) -> Dict[str, Any]:
    name = (name or "").strip()
    with _LOCK:
        s = _LIVE.pop(name, None)
    if not s:
        return {"ok": False, "message": "نشست بازی نیست"}
    ctx = s.get("context")
    if ctx is not None:
        try:
            ctx.close()
        except Exception:
            pass
    for p in s.get("procs", []):
        _kill(p)
    # پروفایل روی دیسک می‌ماند (کوکی‌ها/لاگین دست‌نخورده)
    return {"ok": True, "message": "نشست بسته شد؛ پروفایل روی دیسک باقی ماند"}


def close_all() -> None:
    with _LOCK:
        names = list(_LIVE.keys())
    for n in names:
        try:
            close_remote(n)
        except Exception:
            pass


def reap_idle() -> int:
    """بستن نشست‌های بی‌کار (بیش از IDLE_TIMEOUT)."""
    now = time.time()
    stale: List[str] = []
    with _LOCK:
        for k, v in _LIVE.items():
            if now - float(v.get("last_activity", now)) > IDLE_TIMEOUT_SEC:
                stale.append(k)
    for k in stale:
        try:
            close_remote(k)
        except Exception:
            pass
    return len(stale)


def verify_login(accounts_dir: str, name: str) -> Dict[str, Any]:
    """چک می‌کند پروفایل لاگین‌شده هست (برای «کپچا حل شد / ادامه بده»)."""
    name = (name or "").strip()
    from marketing_divar.chromium_profile import cookies_look_logged_in, _cookies_from_sqlite
    prof = _chromium_dir(accounts_dir, name)
    disk = _cookies_from_sqlite(prof)
    ok = cookies_look_logged_in(disk)
    return {"ok": True, "logged_in": bool(ok), "cookie_count": len(disk)}


def cleanup_orphans() -> int:
    """پاکسازی پردازش‌های یتیم Xvfb/x11vnc/websockify (بعد از ری‌استارت)."""
    if psutil is None:
        return 0
    killed = 0
    ours = set()
    with _LOCK:
        for s in _LIVE.values():
            for p in s.get("procs", []):
                try:
                    ours.add(p.pid)
                except Exception:
                    pass
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            cmd = " ".join(proc.info.get("cmdline") or [])
        except Exception:
            continue
        if any(t in cmd for t in ("Xvfb :1", "x11vnc -display", "websockify")):
            if proc.pid in ours:
                continue
            try:
                proc.kill()
                killed += 1
            except Exception:
                pass
    return killed


def _kill(p: Optional[subprocess.Popen]) -> None:
    if p is None:
        return
    try:
        p.terminate()
    except Exception:
        pass
    try:
        p.wait(timeout=3)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass
