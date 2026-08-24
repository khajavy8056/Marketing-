# -*- coding: utf-8 -*-
"""آزادسازی اکانت: اول با همان سشن به دیوار بزن؛ اگر پازل رفته بود خودکار باز کن."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

from .accounts import AccountManager
from .client import DivarAuthError, DivarClient
from .rate import RateLimiter

_watch_stop = threading.Event()
_watch_thread: Optional[threading.Thread] = None


def try_release_account(mgr: AccountManager, name: str,
                        base_url: Optional[str] = None,
                        force: bool = False,
                        reason: str = "operator") -> Dict[str, Any]:
    """با همان اکانت مسدود به دیوار می‌زند. اگر دیگر پازل نخواهد → active."""
    name = (name or "").strip().lower().replace(" ", "-")
    if not name or not mgr.has_token(name):
        return {"ok": False, "cleared": False, "state": "missing",
                "message": "اکانت پیدا نشد", "divar_url": "https://divar.ir"}
    if force:
        mgr.release(name)
        return {"ok": True, "cleared": True, "state": "clear", "forced": True,
                "message": "آزاد شد (دستی)", "divar_url": "https://divar.ir"}
    cl = DivarClient(
        session_path=str(mgr.session_path(name)),
        base_url=base_url,
        limiter=RateLimiter(phone_delay=0, search_delay=0, page_delay=0, jitter=0))
    try:
        res = cl.probe_gate()
    except DivarAuthError as e:
        mgr.set_status(name, "relogin", note=str(e))
        return {"ok": False, "cleared": False, "state": "relogin",
                "message": str(e), "divar_url": "https://divar.ir"}
    mgr.record_probe(name, res)
    if res.get("ok"):
        mgr.set_status(name, "active", note=f"دیوار باز شد ({reason})")
        out = dict(res)
        out.update({"ok": True, "cleared": True})
        return out
    if res.get("state") == "relogin":
        mgr.set_status(name, "relogin", note=res.get("message") or "")
    out = dict(res)
    out.update({"ok": True, "cleared": False, "open_divar": True,
                "divar_url": res.get("divar_url") or "https://divar.ir"})
    return out


def next_probe_wait(captcha_age_sec: float) -> float:
    """بعد از پیام تلگرام زود چک کن (گوشی)؛ بعد هر ۱۲ دقیقه."""
    if captcha_age_sec < 20 * 60:
        return 120.0
    return 12 * 60.0


def watch_loop(mgr_fn: Callable[[], AccountManager],
               db_path_fn: Callable[[], str],
               base_url_fn: Callable[[], Optional[str]],
               on_cleared: Optional[Callable[[str, Dict[str, Any]], None]] = None,
               sleeper=time.sleep) -> None:
    last: Dict[str, float] = {}
    since: Dict[str, float] = {}
    while not _watch_stop.is_set():
        sleeper(20)
        if _watch_stop.is_set():
            return
        try:
            mgr = mgr_fn()
            now = time.time()
            names = []
            for a in mgr.snapshot(db_path_fn()):
                if a.get("status") == "captcha":
                    names.append(a["name"])
                    since.setdefault(a["name"], now)
            for name in list(since):
                if name not in names:
                    since.pop(name, None)
                    last.pop(name, None)
            for name in names:
                age = now - since.get(name, now)
                if now - last.get(name, 0) < next_probe_wait(age):
                    continue
                last[name] = now
                res = try_release_account(mgr, name, base_url=base_url_fn(),
                                          reason="auto-probe")
                if res.get("cleared") and on_cleared:
                    try:
                        on_cleared(name, res)
                    except Exception:
                        pass
        except Exception:
            pass


def start_watch(mgr_fn: Callable[[], AccountManager],
                db_path_fn: Callable[[], str],
                base_url_fn: Callable[[], Optional[str]],
                on_cleared: Optional[Callable[[str, Dict[str, Any]], None]] = None) -> None:
    global _watch_thread
    if _watch_thread and _watch_thread.is_alive():
        return
    _watch_stop.clear()
    _watch_thread = threading.Thread(
        target=watch_loop, args=(mgr_fn, db_path_fn, base_url_fn, on_cleared),
        daemon=True)
    _watch_thread.start()


def stop_watch() -> None:
    _watch_stop.set()
