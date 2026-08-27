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
MELI_DELIVERY = "https://rest.payamak-panel.com/api/SendSMS/GetDeliveries2"


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


def _recid_of(result: Dict[str, Any]) -> str:
    """RecId عددی را از خروجی ارسال استخراج می‌کند (برای گزارش تحویل)."""
    if not isinstance(result, dict):
        return ""
    msg = str(result.get("message") or "")
    if msg.startswith("recid="):
        return msg[len("recid="):].strip()
    raw = result.get("raw") or {}
    val = raw.get("Value") if isinstance(raw, dict) else None
    try:
        n = int(float(str(val)))
    except (TypeError, ValueError):
        return ""
    return str(n) if n > 2000 else ""


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
    result = {"ok": ok, "message": detail,
              "raw": body if isinstance(body, dict) else {}}
    if ok:
        result["recid"] = _recid_of(result)
    return result


def delivery_melipayamak(username: str, password: str, recid: str,
                         http_post=None) -> Dict[str, Any]:
    """وضعیت تحویل یک پیامک با RecId (مستند رسمی GetDeliveries2).

    خروجی status یکی از: delivered | pending | failed | unknown
    """
    if not (username and password and recid):
        return {"ok": False, "status": "unknown",
                "message": "نام کاربری، رمز و RecId لازم است"}
    poster = http_post
    if poster is None:
        if requests is None:
            return {"ok": False, "status": "unknown",
                    "message": "کتابخانه requests نصب نیست"}
        poster = lambda url, data, timeout=20: requests.post(url, data=data, timeout=timeout)
    try:
        r = poster(MELI_DELIVERY, {
            "username": username, "password": password, "recId": recid,
        }, timeout=20)
        body = r.json() if hasattr(r, "json") else r
    except Exception as e:
        return {"ok": False, "status": "unknown",
                "message": f"{type(e).__name__}: {e}"}
    return interpret_delivery(body if isinstance(body, dict) else {}, recid)


def interpret_delivery(body: Any, recid: str = "") -> Dict[str, Any]:
    """پاسخ GetDeliveries2 را به وضعیت خوانا تبدیل می‌کند.

    کدهای متعارف ملی‌پیامک برای وضعیت تحویل (DeliveryStatus):
      1, 4 → delivered   |   2, 8 → failed
      0, 3, 5, 6 → pending (هنوز در صف/اپراتور)
    """
    val = None
    if isinstance(body, dict):
        val = body.get("Value", body.get("value"))
        if isinstance(val, list) and val and isinstance(val[0], dict):
            # GetDeliveries2 گاهی لیست [{recId, status}] برمی‌گرداند
            st = val[0].get("status") or val[0].get("Status")
            val = st
    try:
        code = int(float(str(val)))
    except (TypeError, ValueError):
        code = -1
    if code in (1, 4):
        return {"ok": True, "status": "delivered",
                "message": "تحویل داده شد", "raw": body}
    if code in (2, 8):
        return {"ok": False, "status": "failed",
                "message": "تحویل نشد (عدم دریافت توسط مخاطب)", "raw": body}
    if code in (0, 3, 5, 6):
        return {"ok": True, "status": "pending",
                "message": "در صف ارسال/در انتظار تحویل", "raw": body}
    return {"ok": True, "status": "unknown",
            "message": f"وضعیت ناشناخته ({body})", "raw": body}


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
              "sms_line_number", "sms_auto_on_new", "sms_daily_limit"):
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
