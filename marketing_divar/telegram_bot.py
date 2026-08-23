# -*- coding: utf-8 -*-
"""ربات تلگرام ادمین — گزارش امروز، صف، آزادسازی اکانت.

فقط chat_id تنظیم‌شده جواب می‌گیرد. بدون توکن، هیچ درخواستی نمی‌زند.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

_stop = threading.Event()
_thread: Optional[threading.Thread] = None


def build_status_text(db_path: str, cfg: Dict[str, Any],
                      running: bool = False, tick: int = 0) -> str:
    from .accounts import AccountManager
    from .db import chat_queue, connect, pending_phone, quota_today, stats
    con = connect(db_path)
    try:
        q = quota_today(con)
        pend = len(pending_phone(con))
        chat = len(chat_queue(con))
        st = [dict(r) for r in stats(con)]
        found = sum(int(r.get("with_phone") or 0) for r in st)
        total = sum(int(r.get("total") or 0) for r in st)
        sms_n = int(q.get("sms") or 0)
    finally:
        con.close()
    ip_lim = cfg.get("ip_daily_limit", 240)
    try:
        from . import store
        kws = [k["keyword"] for k in store.keywords_list(db_path) if k.get("active")]
    except Exception:
        kws = []
    lines = [
        "خواجوی لید — گزارش",
        f"مانیتور: {'روشن' if running else 'خاموش'}" + (f" (دور {tick})" if running else ""),
        f"شماره امروز: {q['phones']} از سقف IP {ip_lim}",
        f"جستجوی امروز: {q['searches']} | پیامک امروز: {sms_n}",
        f"صف شماره: {pend} | فقط‌چت: {chat}",
        f"کل سرنخ / شماره‌دار: {total} / {found}",
    ]
    if kws:
        lines.append("کلمات: " + "، ".join(kws[:12]))
    try:
        for a in AccountManager(cfg).snapshot(db_path):
            lines.append(f"اکانت {a['name']}: {a['status']} (امروز {a['phones_today']})")
    except Exception:
        pass
    return "\n".join(lines)


def handle_command(text: str, db_path: str, cfg: Dict[str, Any],
                   running: bool = False, tick: int = 0) -> str:
    """پاسخ متنی یک فرمان ادمین (بدون شبکه)."""
    raw = (text or "").strip()
    cmd = raw.split()[0].lower() if raw else ""
    if cmd in ("/start", "/help"):
        return ("خواجوی لید\n"
                "/status گزارش امروز\n"
                "/today همان گزارش کوتاه\n"
                "/leads سرنخ‌های شماره‌دار امروز\n"
                "/release نام‌اکانت  آزادسازی بعد از حل کپچا")
    if cmd in ("/status", "/today"):
        return build_status_text(db_path, cfg, running=running, tick=tick)
    if cmd == "/leads":
        from .db import connect
        con = connect(db_path)
        try:
            rows = con.execute(
                "SELECT title, phone FROM leads WHERE phone_status='found' "
                "AND date(first_seen_at)=date('now','localtime') "
                "ORDER BY id DESC LIMIT 8").fetchall()
        finally:
            con.close()
        if not rows:
            return "امروز سرنخ شماره‌دار جدید نیست"
        return "سرنخ‌های امروز:\n" + "\n".join(
            f"{r['phone']} — {(r['title'] or '')[:40]}" for r in rows)
    if cmd == "/release" and len(raw.split()) > 1:
        name = raw.split()[1]
        from .accounts import AccountManager
        mgr = AccountManager(cfg)
        if not mgr.has_token(name):
            return f"اکانت «{name}» پیدا نشد"
        mgr.release(name)
        return f"اکانت {name} آزاد شد"
    return "فرمان ناشناخته. /help"


def _poll_loop(cfg_fn: Callable[[], Dict[str, Any]], db_path: str,
               state_fn: Optional[Callable[[], Dict[str, Any]]] = None) -> None:
    offset = 0
    while not _stop.is_set():
        cfg = cfg_fn() or {}
        notify = cfg.get("notify") or {}
        token = notify.get("telegram_bot_token") or ""
        allow = str(notify.get("telegram_chat_id") or "")
        if not token or not allow or requests is None:
            _stop.wait(8)
            continue
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                params={"timeout": 20, "offset": offset}, timeout=30)
            data = r.json() if r.status_code == 200 else {}
        except Exception:
            _stop.wait(6)
            continue
        for upd in data.get("result") or []:
            offset = max(offset, int(upd.get("update_id", 0)) + 1)
            msg = upd.get("message") or {}
            chat = str((msg.get("chat") or {}).get("id") or "")
            if chat != allow:
                continue
            st = state_fn() if state_fn else {}
            reply = handle_command(msg.get("text") or "", db_path, cfg,
                                   running=bool(st.get("running")),
                                   tick=int(st.get("tick") or 0))
            try:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": allow, "text": reply}, timeout=10)
            except Exception:
                pass


def start_bot(cfg_fn: Callable[[], Dict[str, Any]], db_path: str,
              state_fn: Optional[Callable[[], Dict[str, Any]]] = None) -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_poll_loop,
                               args=(cfg_fn, db_path, state_fn), daemon=True)
    _thread.start()


def stop_bot() -> None:
    _stop.set()
