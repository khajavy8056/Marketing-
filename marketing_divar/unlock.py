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
    if res.get("body") and not res.get("ok"):
        mgr.record_block(name, str(res.get("body") or ""))
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


def confirm_captcha_phone(mgr: AccountManager, name: str, db_path: str,
                         base_url: Optional[str] = None) -> Dict[str, Any]:
    """Operator says captcha is solved: free this account and try ONE queued phone."""
    name = (name or "").strip()
    if not name:
        return {"ok": False, "cleared": False, "phone_tried": False,
                "message": "نام اکانت خالی است"}
    try:
        from .chromium_profile import safe_name
        name = safe_name(name)
    except Exception:
        name = name.replace(" ", "-")
    mgr.release(name)
    if not mgr.has_token(name):
        return {"ok": True, "cleared": True, "phone_tried": False, "state": "clear",
                "message": "اکانت آزاد شد. برای گرفتن شماره، کد پیامک (توکن API) همین اکانت لازم است."}
    from .client import DivarAuthError, DivarBlockedError, DivarClient
    from .db import (bump_quota, connect, log_operation, mark_processing,
                     pending_phone, set_phone)
    from .rate import RateLimiter
    con = connect(db_path)
    try:
        rows = pending_phone(con, limit=1, newest_first=True)
        if not rows:
            return {"ok": True, "cleared": True, "phone_tried": False, "state": "clear",
                    "message": "اکانت آزاد شد. صف شماره خالی است — اسکن را روشن کنید."}
        row = rows[0]
        token = row["token"]
        mark_processing(con, token)
        cl = DivarClient(
            session_path=str(mgr.session_path(name)),
            base_url=base_url,
            limiter=RateLimiter(phone_delay=0, search_delay=0, jitter=0))
        started = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            res = cl.get_phone(token)
        except DivarBlockedError as e:
            con.execute(
                "UPDATE leads SET phone_status='pending', last_error=? WHERE token=?",
                (str(e)[:200], token))
            con.commit()
            mgr.set_status(name, "captcha", note=str(e))
            mgr.record_block(
                name, getattr(e, "body", "") or "",
                token=token,
                url=(row["url"] if "url" in row.keys() else "") or "")
            log_operation(con, token=token, account=name, operation="contact",
                          result="captcha", error=str(e), started_at=started)
            return {"ok": True, "cleared": False, "phone_tried": True,
                    "state": "captcha",
                    "message": "هنوز پازل می‌خواهد — در همان پروفایل حل کنید و دوباره «کپچا حل شد» را بزنید."}
        except DivarAuthError as e:
            con.execute(
                "UPDATE leads SET phone_status='pending', last_error=? WHERE token=?",
                (str(e)[:200], token))
            con.commit()
            mgr.set_status(name, "relogin", note=str(e))
            return {"ok": False, "cleared": False, "phone_tried": True,
                    "state": "relogin",
                    "message": "توکن API رد شد — دوباره کد پیامک بگیرید."}
        except Exception as e:
            con.execute(
                "UPDATE leads SET phone_status='pending', last_error=? WHERE token=?",
                (str(e)[:200], token))
            con.commit()
            return {"ok": False, "cleared": True, "phone_tried": True,
                    "state": "error",
                    "message": "آزاد شد ولی این آگهی خطا داد: %s" % e}
        st = res.get("status")
        if st == "error":
            con.execute(
                "UPDATE leads SET phone_status='pending', last_error=? WHERE token=?",
                ((res.get("message") or "شماره گرفته نشد")[:200], token))
            con.commit()
            log_operation(con, token=token, account=name, operation="contact",
                          result="error", error=res.get("message"),
                          started_at=started)
            return {"ok": True, "cleared": True, "phone_tried": True,
                    "state": "clear",
                    "message": "اکانت آزاد است. این آگهی شماره نداد و در صف ماند — دوباره بزنید."}
        set_phone(con, token, res)
        log_operation(con, token=token, account=name, operation="contact",
                      result=st, phone=res.get("phone"),
                      error=res.get("message"), started_at=started)
        bump_quota(con, "phones")
        mgr.record_use(db_path, name)
        con.commit()
        if st == "found":
            msg = "کپچا رفع شد — شماره گرفته شد: %s" % (res.get("phone") or "")
        elif st == "hidden":
            msg = "کپچا رفع شد — این آگهی فقط چت است. شماره‌گیری ادامه می‌یابد."
        else:
            msg = "کپچا رفع شد — نتیجه: %s" % st
        return {"ok": True, "cleared": True, "phone_tried": True, "state": "clear",
                "status": st, "phone": res.get("phone") or "", "message": msg}
    finally:
        con.close()


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
