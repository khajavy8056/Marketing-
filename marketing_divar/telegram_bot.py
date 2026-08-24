# -*- coding: utf-8 -*-
"""ربات تلگرام ادمین — گزارش، سرنخ، خروجی اکسل، دکمه‌های پایین.

فقط chat_id تنظیم‌شده جواب می‌گیرد. بدون توکن، هیچ درخواستی نمی‌زند.
"""

from __future__ import annotations

import csv
import io
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

_stop = threading.Event()
_thread: Optional[threading.Thread] = None

REPLY_KEYBOARD = {
    "keyboard": [
        [{"text": "📊 گزارش امروز"}, {"text": "📞 سرنخ‌های امروز"}],
        [{"text": "⬇️ خروجی اکسل"}, {"text": "ℹ️ راهنما"}],
    ],
    "resize_keyboard": True,
}

_ALIASES = {
    "/start": "help", "/help": "help", "راهنما": "help",
    "ℹ️ راهنما": "help",
    "/status": "status", "/today": "status",
    "گزارش": "status", "گزارش امروز": "status", "📊 گزارش امروز": "status",
    "/leads": "leads", "سرنخ‌ها": "leads", "سرنخ‌های امروز": "leads",
    "📞 سرنخ‌های امروز": "leads",
    "/export": "export", "اکسل": "export", "خروجی اکسل": "export",
    "⬇️ خروجی اکسل": "export",
}


def _norm_cmd(text: str) -> Tuple[str, str]:
    raw = (text or "").strip()
    key = raw.split()[0] if raw else ""
    mapped = _ALIASES.get(raw) or _ALIASES.get(key.lower() if key.startswith("/") else key)
    return mapped or "", raw


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
        "مارکتینگ دیوار — گزارش",
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


def build_leads_text(db_path: str) -> str:
    from .db import connect
    con = connect(db_path)
    try:
        rows = con.execute(
            "SELECT title, phone, first_seen_at, phone_checked_at FROM leads "
            "WHERE phone_status='found' AND date(first_seen_at)=date('now','localtime') "
            "ORDER BY id DESC LIMIT 8").fetchall()
        n = con.execute(
            "SELECT COUNT(*) c FROM leads WHERE phone_status='found' "
            "AND date(first_seen_at)=date('now','localtime')").fetchone()["c"]
    finally:
        con.close()
    if not rows:
        return "امروز سرنخ شماره‌دار جدید نیست"
    lines = [f"سرنخ‌های امروز ({n} مورد):"]
    for r in rows:
        when = r["phone_checked_at"] or r["first_seen_at"] or "—"
        lines.append(f"{r['phone']} — {(r['title'] or '')[:36]}\n  استخراج: {when}")
    return "\n".join(lines)


def export_excel_bytes(db_path: str, only_phone: bool = True) -> Tuple[bytes, str, int]:
    """CSV سازگار با اکسل — با تاریخ/ساعت کشف و استخراج."""
    from .db import connect
    con = connect(db_path)
    try:
        q = ("SELECT title, phone, keyword, city, phone_status, sms_status, "
             "first_seen_at, phone_checked_at, published_at, sms_sent_at, url "
             "FROM leads")
        if only_phone:
            q += " WHERE phone_status='found'"
        q += " ORDER BY id DESC"
        rows = con.execute(q).fetchall()
    finally:
        con.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["عنوان", "شماره", "کلمه کلیدی", "شهر", "وضعیت شماره", "وضعیت پیامک",
                "تاریخ‌ساعت کشف", "تاریخ‌ساعت استخراج شماره", "زمان انتشار آگهی",
                "تاریخ‌ساعت ارسال پیامک", "لینک"])
    for r in rows:
        w.writerow(list(r))
    data = buf.getvalue().encode("utf-8-sig")
    name = f"divar_marketing_leads_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    return data, name, len(rows)


def handle_command(text: str, db_path: str, cfg: Dict[str, Any],
                   running: bool = False, tick: int = 0) -> str:
    """پاسخ متنی یک فرمان ادمین (بدون شبکه)."""
    mapped, raw = _norm_cmd(text)
    if mapped == "help" or raw in ("/start",):
        return ("مارکتینگ دیوار\n"
                "دکمه‌های پایین ربات را بزنید.\n"
                "/status گزارش امروز\n"
                "/today همان گزارش\n"
                "/leads سرنخ‌های شماره‌دار امروز\n"
                "/export خروجی اکسل با تاریخ و ساعت استخراج\n"
                "/release نام‌اکانت  آزادسازی بعد از حل کپچا")
    if mapped == "status":
        return build_status_text(db_path, cfg, running=running, tick=tick)
    if mapped == "leads":
        return build_leads_text(db_path)
    if mapped == "export":
        _data, name, n = export_excel_bytes(db_path)
        return f"خروجی اکسل آماده است ({n} ردیف) — {name}"
    if (raw.split()[0].lower() if raw else "") == "/release" and len(raw.split()) > 1:
        name = raw.split()[1]
        from .accounts import AccountManager
        mgr = AccountManager(cfg)
        if not mgr.has_token(name):
            return f"اکانت «{name}» پیدا نشد"
        mgr.release(name)
        return f"اکانت {name} آزاد شد"
    return "فرمان ناشناخته. دکمهٔ راهنما را بزنید."


def handle_update(text: str, db_path: str, cfg: Dict[str, Any],
                  running: bool = False, tick: int = 0) -> Dict[str, Any]:
    """پاسخ ربات: متن یا فایل اکسل."""
    mapped, _raw = _norm_cmd(text)
    if mapped == "export":
        data, name, n = export_excel_bytes(db_path)
        return {"text": f"خروجی اکسل — {n} سرنخ\nستون‌ها شامل تاریخ و ساعت کشف و استخراج شماره است.",
                "document": data, "filename": name}
    return {"text": handle_command(text, db_path, cfg, running=running, tick=tick),
            "document": None, "filename": ""}


def vip_alert_text(title: str, city: str = "", category: str = "",
                   price: Any = 0, url: str = "", phone: str = "") -> str:
    """هشدار ویژه — آگهی داخل بازه / تیک VIP."""
    lines = ["⭐ ویژه — آگهی منطبق"]
    if phone:
        lines.append(f"شماره: {phone}")
    if city:
        lines.append(f"شهر: {city}")
    if category:
        lines.append(f"دسته: {category}")
    try:
        n = int(price or 0)
    except (TypeError, ValueError):
        n = 0
    if n > 0:
        if n >= 1_000_000:
            lines.append(f"قیمت: {n / 1_000_000:g} میلیون تومان")
        else:
            lines.append(f"قیمت: {n} تومان")
    if title:
        lines.append(f"آگهی: {(title or '')[:80]}")
    if url:
        lines.append(url)
    lines.append(f"زمان: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(lines)


def found_alert_text(title: str, phone: str, extracted_at: str,
                     phones_today: int, sms_note: str = "") -> str:
    lines = [
        "سرنخ جدید پیدا شد",
        f"شماره: {phone}",
        f"آگهی: {(title or '')[:80]}",
        f"استخراج: {extracted_at}",
        f"شماره امروز تا الان: {phones_today}",
    ]
    if sms_note:
        lines.append(sms_note)
    return "\n".join(lines)


def _send_text(token: str, chat_id: str, text: str) -> None:
    if requests is None or not token or ":" not in token:
        return
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text,
              "reply_markup": REPLY_KEYBOARD},
        timeout=10)


def _send_doc(token: str, chat_id: str, data: bytes, filename: str, caption: str) -> None:
    if requests is None or not token or ":" not in token:
        return
    requests.post(
        f"https://api.telegram.org/bot{token}/sendDocument",
        data={"chat_id": chat_id, "caption": caption},
        files={"document": (filename, data, "text/csv")},
        timeout=30)


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
            out = handle_update(msg.get("text") or "", db_path, cfg,
                                running=bool(st.get("running")),
                                tick=int(st.get("tick") or 0))
            try:
                if out.get("document"):
                    _send_doc(token, allow, out["document"], out["filename"],
                              out.get("text") or "خروجی اکسل")
                else:
                    _send_text(token, allow, out.get("text") or "")
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
