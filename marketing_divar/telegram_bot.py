
# -*- coding: utf-8 -*-
"""ربات تلگرام ادمین — گزارش، سرنخ، خروجی اکسل، دکمه‌های پایین + تیرا دستیار شکار.

فقط chat_id تنظیم‌شده جواب می‌گیرد. بدون توکن، هیچ درخواستی نمی‌زند.
تیرا (Tira) — نام شیک مخصوص شکارچی هوشمند — هم از همین ربات با دکمه مخصوص قابل دسترسی است.
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

# ── تیرا — دستیار شکار حرفه‌ای — نام شیک و مخصوص ──
AI_NAME = "تیرا"
AI_KEYBOARD_TEXT = f"🧠 {AI_NAME} - دستیار شکار"
AI_APPLY_TEXT = f"⭐ ست کردن تنظیمات {AI_NAME}"
AI_CANCEL_TEXT = f"❌ خروج از {AI_NAME}"

REPLY_KEYBOARD = {
    "keyboard": [
        [{"text": "📊 گزارش امروز"}, {"text": "📞 سرنخ‌های امروز"}],
        [{"text": "📋 همه شماره‌ها"}, {"text": "🚨 آلارم‌های مهم"}],
        [{"text": AI_KEYBOARD_TEXT}, {"text": "⬇️ خروجی اکسل"}],
        [{"text": "ℹ️ راهنما"}],
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
            {"id": "ai", "type": "Simple", "button_text": AI_KEYBOARD_TEXT},
            {"id": "export", "type": "Simple", "button_text": "⬇️ خروجی اکسل"},
        ]},
        {"buttons": [
            {"id": "help", "type": "Simple", "button_text": "ℹ️ راهنما"},
        ]},
    ],
}

AI_REPLY_KEYBOARD = {
    "keyboard": [
        [{"text": AI_APPLY_TEXT}, {"text": AI_CANCEL_TEXT}],
        [{"text": "ℹ️ راهنما"}],
    ],
    "resize_keyboard": True,
}

AI_RUBIKA_KEYPAD = {
    "rows": [
        {"buttons": [
            {"id": "ai_apply", "type": "Simple", "button_text": AI_APPLY_TEXT},
            {"id": "ai_cancel", "type": "Simple", "button_text": AI_CANCEL_TEXT},
        ]},
        {"buttons": [
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
    "/ai": "ai", "/tira": "ai", "تیرا": "ai",
    "🧠 تیرا - دستیار شکار": "ai", "🧠 تیرا": "ai", "دستیار شکار": "ai",
    "ai": "ai", "ai_apply": "ai_apply", "ai_cancel": "ai_cancel",
    "⭐ ست کردن تنظیمات تیرا": "ai_apply", "⭐ ست کردن تنظیمات": "ai_apply",
    "❌ خروج از تیرا": "ai_cancel",
    "status": "status", "leads": "leads", "all": "all",
    "alerts": "alerts", "export": "export", "help": "help",
}

# ── حافظه ویزارد برای هر چت ──
_AI_SESSIONS: Dict[str, Any] = {}

def _ai_sid(chat_id: str) -> str:
    return f"tg_{chat_id}"

def _get_ai_wizard(chat_id: str):
    from .hunter_ai_wizard import get_wizard
    return get_wizard(_ai_sid(chat_id))

def _ai_apply_config(db_path: str, chat_id: str) -> str:
    try:
        from . import store
        wiz = _get_ai_wizard(chat_id)
        cfg = wiz.build_config()
        if not cfg or not cfg.get("keywords"):
            return "هنوز تنظیماتی آماده نیست — اول با تیرا صحبت کن تا کارت آماده بشه 😅"
        cities = None
        try:
            specs = store.keywords_active_specs(db_path)
            if specs and specs[0].get("cities"):
                cities = specs[0].get("cities")
        except Exception:
            cities = None
        added = 0
        for kw in cfg.get("keywords", []):
            keyword = kw.get("keyword") or kw.get("model") or ""
            category = kw.get("category") or "mobile-phones"
            price_min = int(kw.get("price_min") or 0)
            price_max = int(kw.get("price_max") or 0)
            hunter_adv = kw.get("hunter_adv") or {}
            ok = store.keywords_add(
                db_path, keyword, cities, category,
                price_min=price_min, price_max=price_max,
                vip=True, hunter=True, hunter_adv=hunter_adv
            )
            if ok:
                added += 1
        _AI_SESSIONS.pop(str(chat_id), None)
        wiz.reset()
        return f"{AI_NAME}: {added} تنظیم شکارچی ست شد ✅ دیوار و شیپور هر دو فعال — مانیتور را از پنل شروع کن 🚀\n{cfg.get('summary','')}"
    except Exception as e:
        return f"خطا در ست کردن: {e}"

def _ai_handle(db_path: str, chat_id: str, text: str) -> Tuple[str, str]:
    """return (reply, keyboard_type='main'|'ai')"""
    try:
        wiz = _get_ai_wizard(chat_id)
        if text in (AI_CANCEL_TEXT, "/cancel", "لغو", "خروج", "ai_cancel"):
            wiz.reset()
            _AI_SESSIONS.pop(str(chat_id), None)
            return f"{AI_NAME}: باشه، از حالت شکار اومدم بیرون 😎 هر وقت خواستی دوباره دکمه 🧠 {AI_NAME} رو بزن", "main"
        if text in (AI_APPLY_TEXT, "ai_apply"):
            msg = _ai_apply_config(db_path, chat_id)
            return msg, "main"
        # شروع
        if text in (AI_KEYBOARD_TEXT, "ai", "/ai", "/tira", "تیرا", "🧠 تیرا", "🧠 تیرا - دستیار شکار", "دستیار شکار"):
            res = wiz.start()
            intro = f"سلام! من {AI_NAME} هستم 👋 دستیار شکار حرفه‌ای تو! 🎯\nقراره با هم سود کنیم — مثل یه رفیق تهرانی، باحال و پرانرژی 😎\n\n"
            _AI_SESSIONS[str(chat_id)] = {"active": True}
            return intro + res.get("reply",""), "ai"
        # اگر داخل سشن هستیم یا محصولات داریم
        if str(chat_id) in _AI_SESSIONS or wiz.state.get("products") or wiz.state.get("step") not in ("greeting","done"):
            res = wiz.handle_user(text)
            reply = res.get("reply","")
            if res.get("done"):
                reply += f"\n\nبرای ست کردن، دکمه {AI_APPLY_TEXT} رو بزن ⭐"
                _AI_SESSIONS[str(chat_id)] = {"active": True, "done": True}
                return reply, "ai"
            else:
                _AI_SESSIONS[str(chat_id)] = {"active": True}
                return reply, "ai"
        # fallback
        res = wiz.start()
        intro = f"سلام! من {AI_NAME} هستم 👋\n"
        _AI_SESSIONS[str(chat_id)] = {"active": True}
        return intro + res.get("reply",""), "ai"
    except Exception as e:
        return f"{AI_NAME}: خطا {e}", "main"

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
    mapped, raw = _norm_cmd(text)
    # تیرا
    if mapped in ("ai", "ai_apply", "ai_cancel"):
        reply, _kb = _ai_handle(db_path, str(cfg.get("notify",{}).get("telegram_chat_id") or cfg.get("notify",{}).get("bale_chat_id") or cfg.get("notify",{}).get("rubika_chat_id") or "0"), raw)
        # اگر db_path واقعی نداریم برای apply، دوباره با db_path درست تلاش کن اگر apply بود
        if mapped == "ai_apply":
            reply = _ai_apply_config(db_path, str(cfg.get("notify",{}).get("telegram_chat_id") or "0"))
        return reply
    if mapped == "help" or raw in ("/start",):
        return (f"مارکتینگ دیوار — {AI_NAME} هم اینجاست! 🎯\n"
                f"سلام! من {AI_NAME} هستم 👋 دستیار شکار حرفه‌ای\n"
                "دکمه‌های پایین ربات را بزنید.\n"
                f"{AI_KEYBOARD_TEXT} — صحبت با {AI_NAME} برای تنظیم شکارچی\n"
                "/status گزارش امروز\n"
                "/leads سرنخ‌های شماره‌دار امروز\n"
                "/all همه شماره‌ها\n"
                "/alerts آلارم‌های مهم (کپچا / لاگین)\n"
                "/export خروجی اکسل\n"
                "/release نام‌اکانت آزادسازی\n"
                f"{AI_APPLY_TEXT} ست کردن تنظیمات {AI_NAME}\n")
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
                  running: bool = False, tick: int = 0, chat_id: str = "") -> Dict[str, Any]:
    mapped, raw = _norm_cmd(text)
    # تشخیص سشن تیرا فعال برای این چت
    cid = str(chat_id or cfg.get("notify",{}).get("telegram_chat_id") or cfg.get("notify",{}).get("bale_chat_id") or cfg.get("notify",{}).get("rubika_chat_id") or "")
    # اگر داخل تیرا هستیم یا دکمه تیرا زده شده، مستقیم به تیرا بده
    if mapped in ("ai", "ai_apply", "ai_cancel") or cid in _AI_SESSIONS:
        # اگر apply است و db_path داریم
        if mapped == "ai_apply":
            txt = _ai_apply_config(db_path, cid)
            return {"text": txt, "document": None, "filename": "", "keyboard": "main"}
        reply, kb_type = _ai_handle(db_path, cid, raw)
        # اگر کاربر ست کردن زد و ما db_path نداریم، دوباره با db_path درست apply کن
        if "ست شد" in reply and "تنظیم" in reply:
            kb_type = "main"
        extra_kb = AI_REPLY_KEYBOARD if kb_type == "ai" else REPLY_KEYBOARD
        extra_rb = AI_RUBIKA_KEYPAD if kb_type == "ai" else RUBIKA_CHAT_KEYPAD
        return {"text": reply, "document": None, "filename": "", "keyboard": extra_kb, "rubika_keypad": extra_rb}
    if mapped == "export":
        data, name, n = export_excel_bytes(db_path)
        return {"text": f"خروجی اکسل — {n} سرنخ\nستون‌ها شامل تاریخ و ساعت کشف و استخراج شماره است.",
                "document": data, "filename": name}
    txt = handle_command(text, db_path, cfg, running=running, tick=tick)
    return {"text": txt, "document": None, "filename": ""}


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





def _send_text(cfg: Dict[str, Any], chat_id: str, text: str, keyboard: Optional[Dict[str, Any]] = None) -> None:
    from .notifier import telegram_request
    payload: Dict[str, Any] = {"chat_id": chat_id, "text": text,
                               "reply_markup": keyboard or REPLY_KEYBOARD}
    telegram_request(cfg, "sendMessage", json=payload, timeout=12)


def _send_doc(cfg: Dict[str, Any], chat_id: str, data: bytes,
              filename: str, caption: str) -> None:
    from .notifier import telegram_request
    telegram_request(cfg, "sendDocument",
                     data={"chat_id": chat_id, "caption": caption},
                     files={"document": (filename, data, "text/csv")},
                     timeout=30)


def _dispatch(cfg: Dict[str, Any], db_path: str, text: str,
              state_fn: Optional[Callable[[], Dict[str, Any]]],
              send_text, send_doc, chat_id: str = "") -> None:
    st = state_fn() if state_fn else {}
    out = handle_update(text or "", db_path, cfg,
                        running=bool(st.get("running")),
                        tick=int(st.get("tick") or 0),
                        chat_id=chat_id)
    if out.get("document"):
        send_doc(out["document"], out["filename"], out.get("text") or "خروجی اکسل")
    else:
        # اگر کیبورد اختصاصی تیرا دارد، از آن استفاده کن
        kb = out.get("keyboard")
        if kb:
            # send_text با کیبورد سفارشی
            try:
                send_text(out.get("text") or "", keyboard=kb)
                return
            except TypeError:
                pass
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
            def stxt(t, kb=None, _chat=dest):
                if kb:
                    _send_text(cfg, _chat, t, keyboard=kb)
                else:
                    _send_text(cfg, _chat, t)

            def sdoc(blob, name, cap, _chat=dest):
                _send_doc(cfg, _chat, blob, name, cap)
        else:
            def stxt(t, kb=None):
                # بله
                payload = {"reply_markup": kb or REPLY_KEYBOARD}
                send_bale(cfg, t, extra=payload)

            def sdoc(blob, name, cap, _chat=dest):
                bale_request(cfg, "sendDocument",
                             data={"chat_id": _chat, "caption": cap},
                             files={"document": (name, blob, "text/csv")},
                             timeout=30)
        try:
            _dispatch(cfg, db_path, text, state_fn, stxt, sdoc, chat_id=dest)
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

        def stxt(t, kb=None):
            kp = kb or RUBIKA_CHAT_KEYPAD
            # اگر تیرا فعال است، کیبورد تیرا
            if isinstance(kb, dict) and "keyboard" in kb:
                # تلگرام کیبورد آمده، برای روبیکا تبدیل کن
                pass
            send_rubika(cfg, t, extra={
                "chat_keypad_type": "New", "chat_keypad": kp if not kb else (kb.get("rubika_keypad") or kp)})

        def sdoc(_blob, _name, cap):
            send_rubika(cfg, cap or "خروجی اکسل آماده است — از پنل دانلود کنید")

        try:
            _dispatch(cfg, db_path, text, state_fn, stxt, sdoc, chat_id=chat)
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
