# -*- coding: utf-8 -*-
"""ارسال پیامک از مسیر رسمی ملی‌پیامک (REST).

مستند رسمی: POST https://rest.payamak-panel.com/api/SendSMS/SendSMS
با username + password پنل ملی‌پیامک + شماره خط اختصاصی.

ارسال از سیم‌کارت شخصیِ گوشی، از ویندوز بدون مودم/اپ اندروید ممکن نیست.
اگر خط اختصاصی از ملی‌پیامک بخرید، همان شماره در «خط ارسال» قرار می‌گیرد.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

MELI_SEND = "https://rest.payamak-panel.com/api/SendSMS/SendSMS"
MELI_CREDIT = "https://rest.payamak-panel.com/api/SendSMS/GetCredit"


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


def maybe_send_for_lead(cfg: Dict[str, Any], lead: Dict[str, Any],
                        template: str, http_post=None) -> Optional[Dict[str, Any]]:
    """اگر ارسال خودکار روشن باشد، برای سرنخ شماره‌دار پیامک می‌زند."""
    if not cfg.get("sms_auto_on_new"):
        return None
    if (cfg.get("sms_provider") or "none") != "melipayamak":
        return None
    phone = (lead.get("phone") or "").strip()
    if not phone:
        return None
    from .messaging import build_message
    safe = {"title": lead.get("title") or "آگهی شما",
            "subtitle": lead.get("subtitle") or "",
            "url": lead.get("url") or ""}
    text = build_message(template or "سلام، آگهی «{title}» را دیدم.", safe)
    return send_melipayamak(
        cfg.get("sms_username") or "",
        cfg.get("sms_password") or cfg.get("sms_api_key") or "",
        phone,
        cfg.get("sms_line_number") or "",
        text,
        http_post=http_post)
