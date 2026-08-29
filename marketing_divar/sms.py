# -*- coding: utf-8 -*-
"""ارسال پیامک از مسیر رسمی ملی‌پیامک (REST).

مستند رسمی: POST https://rest.payamak-panel.com/api/SendSMS/SendSMS
با username + password پنل ملی‌پیامک + شماره خط اختصاصی.

ارسال از سیم‌کارت شخصیِ گوشی، از ویندوز بدون مودم/اپ اندروید ممکن نیست.
اگر خط اختصاصی از ملی‌پیامک بخرید، همان شماره در «خط ارسال» قرار می‌گیرد.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

MELI_SEND = "https://rest.payamak-panel.com/api/SendSMS/SendSMS"
MELI_CREDIT = "https://rest.payamak-panel.com/api/SendSMS/GetCredit"
MELI_RECEIVE = "https://rest.payamak-panel.com/api/ReceiveMessage/GetMessage"
MELI_RECEIVE2 = "https://rest.payamak-panel.com/api/ReceiveMessage/GetMessages"


def interpret_meli(resp: Any) -> Tuple[bool, str]:
    """Value بزرگ‌تر از ۲۰۰۰ = RecId موفق (مستند رسمی)."""
    if not isinstance(resp, dict):
        return False, str(resp)[:160]
    val = resp.get("Value", resp.get("value"))
    try:
        n = int(float(str(val)))
    except (TypeError, ValueError):
        n = -1
    if n > 2000:
        return True, f"recid={n}"
    msg = resp.get("StrRetStatus") or resp.get("RetStatus") or val
    return False, str(msg)[:160]


def send_melipayamak(username: str, password: str, to: str, line: str,
                     text: str, http_post=None) -> Dict[str, Any]:
    """ارسال یک پیامک. http_post قابل تزریق برای تست."""
    if not (username and password and to and line and text):
        return {"ok": False, "message": "نام کاربری، رمز، خط و متن لازم است"}
    poster = http_post
    if poster is None:
        if requests is None:
            return {"ok": False, "message": "کتابخانه requests نصب نیست"}
        poster = lambda url, data, timeout=20: requests.post(url, data=data, timeout=timeout)
    try:
        r = poster(MELI_SEND, {
            "username": username, "password": password,
            "to": to, "from": line, "text": text, "isFlash": False,
        }, timeout=20)
        body = r.json() if hasattr(r, "json") else r
    except Exception as e:
        return {"ok": False, "message": f"{type(e).__name__}: {e}"}
    ok, detail = interpret_meli(body if isinstance(body, dict) else {})
    return {"ok": ok, "message": detail, "raw": body if isinstance(body, dict) else {}}


def credit_melipayamak(username: str, password: str, http_post=None) -> Dict[str, Any]:
    if not (username and password):
        return {"ok": False, "message": "نام کاربری و رمز لازم است"}
    poster = http_post
    if poster is None:
        if requests is None:
            return {"ok": False, "message": "کتابخانه requests نصب نیست"}
        poster = lambda url, data, timeout=20: requests.post(url, data=data, timeout=timeout)
    try:
        r = poster(MELI_CREDIT, {"username": username, "password": password}, timeout=15)
        body = r.json() if hasattr(r, "json") else r
    except Exception as e:
        return {"ok": False, "message": f"{type(e).__name__}: {e}"}
    return {"ok": True, "message": str((body or {}).get("Value", body))[:80],
            "raw": body if isinstance(body, dict) else {}}


def normalize_ir_phone(raw: str) -> str:
    digits = "".join(c for c in (raw or "") if c.isdigit())
    if digits.startswith("98") and len(digits) >= 12:
        digits = "0" + digits[2:]
    if len(digits) == 10 and digits.startswith("9"):
        digits = "0" + digits
    return digits


def compose_sms(template: str, lead: Dict[str, Any]) -> str:
    from .messaging import build_message
    safe = {"title": lead.get("title") or "آگهی شما",
            "subtitle": lead.get("subtitle") or "",
            "url": lead.get("url") or "",
            "city": lead.get("city") or "",
            "keyword": lead.get("keyword") or "",
            "price": lead.get("price") or 0,
            "published_at": lead.get("published_at") or ""}
    return build_message(template or "سلام، آگهی «{title}» را دیدم.", safe)


def parse_inbox_body(body: Any) -> List[Dict[str, str]]:
    """خروجی GetMessage/GetMessages ملی‌پیامک را به فهرست {from,body,date} تبدیل می‌کند."""
    out: List[Dict[str, str]] = []
    if body is None:
        return out
    if isinstance(body, str):
        return out
    data = body
    if isinstance(body, dict):
        data = body.get("Data") or body.get("data") or body.get("Value") or body.get("Messages") or body
    if isinstance(data, dict):
        data = data.get("Messages") or data.get("messages") or [data]
    if not isinstance(data, list):
        return out
    for item in data:
        if not isinstance(item, dict):
            continue
        sender = str(item.get("From") or item.get("from") or item.get("Sender")
                     or item.get("Mobile") or "")
        txt = str(item.get("Body") or item.get("body") or item.get("Text")
                  or item.get("Message") or "")
        when = str(item.get("Date") or item.get("date") or item.get("ReceivedDate") or "")
        if sender or txt:
            out.append({"from": sender, "body": txt, "date": when})
    return out


def receive_melipayamak(username: str, password: str, location: int = 1,
                        count: int = 50, http_post=None) -> Dict[str, Any]:
    """پولینگ صندوق ورودی ملی‌پیامک (وب‌هوک روی ویندوز محلی نداریم).

    مستند: ReceiveMessage/GetMessage و GetMessages با username+password.
    location=1 معمولاً پیام‌های دریافتی است.
    """
    if not (username and password):
        return {"ok": False, "messages": [], "message": "نام کاربری و رمز لازم است"}
    poster = http_post
    if poster is None:
        if requests is None:
            return {"ok": False, "messages": [], "message": "کتابخانه requests نصب نیست"}
        poster = lambda url, data, timeout=20: requests.post(url, data=data, timeout=timeout)
    last_err = ""
    for url in (MELI_RECEIVE, MELI_RECEIVE2):
        try:
            r = poster(url, {
                "username": username, "password": password,
                "location": location, "index": 0, "count": count, "from": "",
            }, timeout=20)
            body = r.json() if hasattr(r, "json") else r
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            continue
        msgs = parse_inbox_body(body)
        return {"ok": True, "messages": msgs, "raw": body if isinstance(body, dict) else {},
                "message": f"{len(msgs)} پیام"}
    return {"ok": False, "messages": [], "message": last_err or "صندوق خوانده نشد"}


def sms_ready(cfg: Dict[str, Any]) -> Tuple[bool, str]:
    if (cfg.get("sms_provider") or "none") != "melipayamak":
        return False, "سرویس‌دهنده ملی‌پیامک نیست"
    if not (cfg.get("sms_username") and
            (cfg.get("sms_password") or cfg.get("sms_api_key"))):
        return False, "نام کاربری و رمز ملی‌پیامک ذخیره نشده"
    if not (cfg.get("sms_line_number") or "").strip():
        return False, "شماره خط ارسال خالی است"
    return True, "آماده"


def live_sms_cfg(db_path: str, fallback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """تنظیمات پیامک را زنده از دیتابیس می‌خواند (بدون نیاز به ری‌استارت مانیتور)."""
    from . import store
    cfg = dict(fallback or {})
    s = store.settings_all(db_path)
    for k in ("sms_provider", "sms_api_key", "sms_username", "sms_password",
              "sms_line_number", "sms_auto_on_new", "sms_daily_limit",
              "sms_inbox_on"):
        cfg[k] = s.get(k, cfg.get(k))
    return cfg


def send_for_lead(cfg: Dict[str, Any], lead: Dict[str, Any],
                  template: str, http_post=None) -> Dict[str, Any]:
    """ارسال همان قالب آماده‌شده به شمارهٔ همین سرنخ — بدون شرط خودکار."""
    ready, why = sms_ready(cfg)
    if not ready:
        return {"ok": False, "message": why}
    phone = normalize_ir_phone(lead.get("phone") or "")
    if not (phone.startswith("09") and len(phone) == 11):
        return {"ok": False, "message": f"شماره نامعتبر: {lead.get('phone')}"}
    text = compose_sms(template, lead)
    return send_melipayamak(
        cfg.get("sms_username") or "",
        cfg.get("sms_password") or cfg.get("sms_api_key") or "",
        phone,
        (cfg.get("sms_line_number") or "").strip(),
        text,
        http_post=http_post)


def maybe_send_for_lead(cfg: Dict[str, Any], lead: Dict[str, Any],
                        template: str, http_post=None) -> Optional[Dict[str, Any]]:
    """اگر ارسال خودکار روشن باشد، همان لحظه پیامک می‌زند."""
    if not cfg.get("sms_auto_on_new"):
        return None
    return send_for_lead(cfg, lead, template, http_post=http_post)
