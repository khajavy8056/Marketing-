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
        [{"text": "📋 همه شماره‌ها"}, {"text": "🚨 آلارم‌های مهم"}],
        [{"text": "⬇️ خروجی اکسل"}, {"text": "ℹ️ راهنما"}],
    ],
    "resize_keyboard": True,
}

RUBIKA_CHAT_KEYPAD = {
    "rows": [
        {"buttons": [
            {"id": "status", "type": "Simple", "button_text": "📊 گزارش امروز"},
            {"id": "leads", "type": "Simple", "button_text": "📞 سرنخ‌های امروز"},
        ]},
        {"buttons": [
            {"id": "all", "type": "Simple", "button_text": "📋 همه شماره‌ها"},
            {"id": "alerts", "type": "Simple", "button_text": "🚨 آلارم‌های مهم"},
        ]},
        {"buttons": [
            {"id": "export", "type": "Simple", "button_text": "⬇️ خروجی اکسل"},
            {"id": "help", "type": "Simple", "button_text": "ℹ️ راهنما"},
        ]},
    ],
}

_ALIASES = {
    "/start": "help", "/help": "help", "راهنما": "help",
    "ℹ️ راهنما": "help",
    "/status": "status", "/today": "status",
    "گزارش": "status", "گزارش امروز": "status", "📊 گزارش امروز": "status",
    "/leads": "leads", "سرنخ‌ها": "leads", "سرنخ‌های امروز": "leads",
    "📞 سرنخ‌های امروز": "leads",
    "/all": "all", "همه شماره‌ها": "all", "📋 همه شماره‌ها": "all",
    "همه شماره‌ها را بفرست": "all",
    "/alerts": "alerts", "آلارم": "alerts", "آلارم‌های مهم": "alerts",
    "🚨 آلارم‌های مهم": "alerts",
    "/export": "export", "اکسل": "export", "خروجی اکسل": "export",
    "⬇️ خروجی اکسل": "export",
    "status": "status", "leads": "leads", "all": "all",
    "alerts": "alerts", "export": "export", "help": "help",
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


def build_all_phones_text(db_path: str) -> str:
    from .db import connect
    con = connect(db_path)
    try:
        rows = con.execute(
            "SELECT title, phone, phone_checked_at, first_seen_at FROM leads "
            "WHERE phone_status='found' AND phone IS NOT NULL AND phone!='' "
            "ORDER BY id DESC LIMIT 40").fetchall()
        n = con.execute(
            "SELECT COUNT(*) c FROM leads WHERE phone_status='found' "
            "AND phone IS NOT NULL AND phone!=''").fetchone()["c"]
    finally:
        con.close()
    if not rows:
        return "هنوز شمارهٔ استخراج‌شده‌ای نیست"
    lines = [f"همه شماره‌ها ({n} مورد — تا ۴۰ تای آخر):"]
    for r in rows:
        when = r["phone_checked_at"] or r["first_seen_at"] or "—"
        lines.append(f"{r['phone']} — {(r['title'] or '')[:36]}\n  {when}")
    return "\n".join(lines)


def build_alerts_text(db_path: str, cfg: Dict[str, Any]) -> str:
    from .accounts import AccountManager
    lines = ["آلارم‌های مهم"]
    try:
        accs = AccountManager(cfg).snapshot(db_path)
    except Exception:
        accs = []
    hot = [a for a in accs if a.get("status") in ("captcha", "relogin")]
    if not hot:
        lines.append("الان اکانت منتظر واکنش نیست.")
    for a in hot:
        lines.append(f"• {a.get('name')}: {a.get('status')} — {a.get('note') or ''}")
        if a.get("last_ad_url"):
            lines.append(f"  {a['last_ad_url']}")
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
                "/all همه شماره‌ها\n"
                "/alerts آلارم‌های مهم (کپچا / لاگین)\n"
                "/export خروجی اکسل با تاریخ و ساعت استخراج\n"
                "/release نام‌اکانت  آزادسازی بعد از حل کپچا")
    if mapped == "status":
        return build_status_text(db_path, cfg, running=running, tick=tick)
    if mapped == "leads":
        return build_leads_text(db_path)
    if mapped == "all":
        return build_all_phones_text(db_path)
    if mapped == "alerts":
        return build_alerts_text(db_path, cfg)
    if mapped == "export":
        _data, name, n = export_excel_bytes(db_path)
        return f"خروجی اکسل آماده است ({n} ردیف) — {name}"
    # تیرا — دستور آزاد از تلگرام/بله/روبیکا (قالب، پایش دسته، راهنمای پیامک، جاروبرقی)
    if not mapped:
        try:
            from .tira_commands import classify_intent, handle_tira_from_bot
            looks_cmd = (raw or "").startswith("/")
            intent = classify_intent(raw)
            if intent.get("kind") or not looks_cmd:
                return handle_tira_from_bot(raw, db_path=db_path, session_id="bot")
        except Exception:
            pass
    if (raw.split()[0].lower() if raw else "") == "/release" and len(raw.split()) > 1:
        name = raw.split()[1]
        from .accounts import AccountManager
        from .unlock import try_release_account
        mgr = AccountManager(cfg)
        if not mgr.has_token(name):
            return f"اکانت «{name}» پیدا نشد"
        res = try_release_account(mgr, name, reason="تلگرام")
        if res.get("cleared"):
            return f"اکانت {name} آزاد شد — دیوار دیگر پازل نمی‌خواهد"
        return (f"اکانت {name} هنوز پازل می‌خواهد. "
                "با همان شماره در دیوار گوشی حل کنید؛ برنامه خودش دوباره چک می‌کند.")
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


def _send_text(cfg: Dict[str, Any], chat_id: str, text: str) -> None:
    from .notifier import telegram_request
    telegram_request(cfg, "sendMessage",
                     json={"chat_id": chat_id, "text": text,
                           "reply_markup": REPLY_KEYBOARD},
                     timeout=12)


def _send_doc(cfg: Dict[str, Any], chat_id: str, data: bytes,
              filename: str, caption: str) -> None:
    from .notifier import telegram_request
    telegram_request(cfg, "sendDocument",
                     data={"chat_id": chat_id, "caption": caption},
                     files={"document": (filename, data, "text/csv")},
                     timeout=30)


def _dispatch(cfg: Dict[str, Any], db_path: str, text: str,
              state_fn: Optional[Callable[[], Dict[str, Any]]],
              send_text, send_doc) -> None:
    st = state_fn() if state_fn else {}
    out = handle_update(text or "", db_path, cfg,
                        running=bool(st.get("running")),
                        tick=int(st.get("tick") or 0))
    if out.get("document"):
        send_doc(out["document"], out["filename"], out.get("text") or "خروجی اکسل")
    else:
        send_text(out.get("text") or "")


def _poll_telegram_like(cfg: Dict[str, Any], db_path: str,
                        state_fn, offset: int, kind: str) -> int:
    from .notifier import bale_request, send_bale, telegram_request
    n = cfg.get("notify") or {}
    if kind == "telegram":
        allow = str(n.get("telegram_chat_id") or "")
        r = telegram_request(cfg, "getUpdates",
                             params={"timeout": 12, "offset": offset},
                             timeout=20)
    else:
        allow = str(n.get("bale_chat_id") or "")
        r = bale_request(cfg, "getUpdates",
                         json={"timeout": 8, "offset": offset, "limit": 50},
                         timeout=16)
    if r is None:
        return offset
    try:
        data = r.json() if r.status_code == 200 else {}
    except Exception:
        return offset
    for upd in data.get("result") or []:
        try:
            offset = max(offset, int(upd.get("update_id", 0)) + 1)
        except Exception:
            continue
        msg = upd.get("message") or {}
        chat = str((msg.get("chat") or {}).get("id") or "")
        if allow and chat != allow:
            continue
        text = msg.get("text") or ""
        dest = chat or allow
        if kind == "telegram":
            def stxt(t, _chat=dest):
                _send_text(cfg, _chat, t)

            def sdoc(blob, name, cap, _chat=dest):
                _send_doc(cfg, _chat, blob, name, cap)
        else:
            def stxt(t):
                send_bale(cfg, t, extra={"reply_markup": REPLY_KEYBOARD})

            def sdoc(blob, name, cap, _chat=dest):
                bale_request(cfg, "sendDocument",
                             data={"chat_id": _chat, "caption": cap},
                             files={"document": (name, blob, "text/csv")},
                             timeout=30)
        try:
            _dispatch(cfg, db_path, text, state_fn, stxt, sdoc)
        except Exception:
            pass
    return offset


def _poll_rubika(cfg: Dict[str, Any], db_path: str, state_fn,
                 offset_id: str) -> str:
    from .notifier import rubika_request, send_rubika
    payload: Dict[str, Any] = {"limit": 50}
    if offset_id:
        payload["offset_id"] = offset_id
    r = rubika_request(cfg, "getUpdates", json=payload, timeout=16)
    if r is None:
        return offset_id
    try:
        body = r.json() or {}
    except Exception:
        return offset_id
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        data = body if isinstance(body, dict) else {}
    nxt = str(data.get("next_offset_id") or offset_id or "")
    updates = data.get("updates") or body.get("updates") or []
    allow = str((cfg.get("notify") or {}).get("rubika_chat_id") or "")
    for upd in updates:
        if not isinstance(upd, dict):
            continue
        inner = upd.get("update") if isinstance(upd.get("update"), dict) else upd
        chat = str(inner.get("chat_id") or "")
        msg = inner.get("new_message") or inner.get("message") or {}
        if not isinstance(msg, dict):
            msg = {}
        text = str(msg.get("text") or "")
        aux = msg.get("aux_data") or inner.get("aux_data") or {}
        if isinstance(aux, dict) and aux.get("button_id"):
            text = str(aux.get("button_id"))
        if allow and chat and chat != allow:
            continue

        def stxt(t):
            send_rubika(cfg, t, extra={
                "chat_keypad_type": "New", "chat_keypad": RUBIKA_CHAT_KEYPAD})

        def sdoc(_blob, _name, cap):
            send_rubika(cfg, cap or "خروجی اکسل آماده است — از پنل دانلود کنید")

        try:
            _dispatch(cfg, db_path, text, state_fn, stxt, sdoc)
        except Exception:
            pass
    return nxt or offset_id


def _poll_loop(cfg_fn: Callable[[], Dict[str, Any]], db_path: str,
               state_fn: Optional[Callable[[], Dict[str, Any]]] = None) -> None:
    tg_off = 0
    bale_off = 0
    rub_off = ""
    while not _stop.is_set():
        cfg = cfg_fn() or {}
        n = cfg.get("notify") or {}
        did = False
        try:
            from .notifier import (bale_configured, rubika_configured,
                                   telegram_configured)
            if telegram_configured(cfg) or (
                    n.get("telegram_enabled", True)
                    and n.get("telegram_bot_token") and n.get("telegram_chat_id")):
                tg_off = _poll_telegram_like(cfg, db_path, state_fn, tg_off, "telegram")
                did = True
            if bale_configured(cfg) or (
                    n.get("bale_enabled", True)
                    and n.get("bale_bot_token") and n.get("bale_chat_id")):
                bale_off = _poll_telegram_like(cfg, db_path, state_fn, bale_off, "bale")
                did = True
            if rubika_configured(cfg) or (
                    n.get("rubika_enabled", True)
                    and n.get("rubika_bot_token") and n.get("rubika_chat_id")):
                rub_off = _poll_rubika(cfg, db_path, state_fn, rub_off)
                did = True
        except Exception:
            pass
        if not did:
            _stop.wait(8)


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
