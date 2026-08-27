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
MELI_BASE_NUMBER = "https://rest.payamak-panel.com/api/SendSMS/BaseServiceNumber"


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


# کدهای خطای متعارف پترن (BaseServiceNumber / SendByBaseNumber) — برای پیام خوانا
_PATTERN_ERRORS = {
    -8: "متن باید با @ شروع شود (قالب پترن)",
    -7: "خطای داخلی — با پشتیبانی تماس بگیرید",
    -6: "متن با متغیرهای تعریف‌شده در پترن همخوانی ندارد (تعداد/ترتیب متغیرها)",
    -5: "کد پترن (bodyId) صحیح نیست یا توسط مدیر سامانه تأیید نشده",
    -4: "خط ارسال تعریف نشده — با پشتیبانی تماس بگیرید",
    -3: "محدودیت تعداد شماره — هر بار فقط یک شماره",
    -2: "کد پترن (bodyId) درج نشده است",
    -1: "دسترسی به وب‌سرویس پترن غیرفعال است",
    0: "نام کاربری یا رمز عبور صحیح نیست",
    2: "اعتبار کافی نیست",
    6: "سامانه در حال بروزرسانی است",
    7: "متن حاوی کلمهٔ فیلترشده است — با واحد اداری تماس بگیرید",
    10: "کاربر موردنظر فعال نیست",
    11: "ارسال نشد",
    12: "مدارک کاربر کامل نیست",
}


def interpret_pattern_result(body: Any) -> Tuple[bool, str]:
    """خروجی BaseServiceNumber: عدد بزرگ = recId موفق؛ منفی/کوچک = خطا."""
    if not isinstance(body, dict):
        return False, str(body)[:160]
    val = body.get("Value", body.get("value"))
    try:
        n = int(float(str(val)))
    except (TypeError, ValueError):
        n = None
    if n is not None and n > 2000:
        return True, f"recid={n}"
    if n is not None and n in _PATTERN_ERRORS:
        return False, _PATTERN_ERRORS[n]
    msg = body.get("StrRetStatus") or body.get("RetStatus") or val
    return False, str(msg)[:160]


def send_melipayamak_pattern(username: str, password: str, to: str,
                             body_id: str, args: list,
                             http_post=None) -> Dict[str, Any]:
    """ارسال پیامک از پترن (خط خدماتی اشتراکی) — بدون نیاز به شمارهٔ خط اختصاصی.

    مستند رسمی: POST rest.payamak-panel.com/api/SendSMS/BaseServiceNumber
    با username + password + bodyId + text (مقادیر متغیرها با ; جدا) + to.
    """
    if not (username and password and to and body_id):
        return {"ok": False, "message": "نام کاربری، رمز، شماره و کد پترن لازم است"}
    poster = http_post
    if poster is None:
        if requests is None:
            return {"ok": False, "message": "کتابخانه requests نصب نیست"}
        poster = lambda url, data, timeout=20: requests.post(url, data=data, timeout=20)
    text = ";".join(str(a) for a in (args or []))
    try:
        r = poster(MELI_BASE_NUMBER, {
            "username": username, "password": password,
            "to": to, "bodyId": body_id, "text": text,
        }, timeout=20)
        body = r.json() if hasattr(r, "json") else r
    except Exception as e:
        return {"ok": False, "message": f"{type(e).__name__}: {e}"}
    ok, detail = interpret_pattern_result(body if isinstance(body, dict) else {})
    result = {"ok": ok, "message": detail,
              "raw": body if isinstance(body, dict) else {}}
    if ok:
        result["recid"] = _recid_of(result)
    return result


# فیلدهای سرنخ که می‌توانند به‌عنوان متغیر پترن استفاده شوند
_PATTERN_FIELDS = ("title", "subtitle", "city", "keyword", "price",
                   "published_at", "url")


def build_pattern_args(cfg: Dict[str, Any], lead: Dict[str, Any]) -> list:
    """مقادیر متغیرهای پترن را به همان ترتیب تعریف‌شده در پنل می‌سازد.

    ترتیب از تنظیم sms_pattern_args می‌آید (فهرست فیلدها با کاما).
    """
    spec = (cfg.get("sms_pattern_args") or "title").strip()
    names = [n.strip().lower() for n in spec.split(",") if n.strip()]
    out = []
    for n in names:
        v = lead.get(n) if isinstance(lead, dict) else None
        if n == "price":
            try:
                v = int(v or 0)
            except (TypeError, ValueError):
                v = 0
            v = f"{v / 1_000_000:g} میلیون" if v >= 1_000_000 else (str(v) if v else "")
        out.append(str(v or "").strip())
    return out


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
    if cfg.get("sms_use_pattern"):
        if not (cfg.get("sms_pattern_bodyid") or "").strip():
            return False, "کد پترن (bodyId) خالی است"
    else:
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
              "sms_use_pattern", "sms_pattern_bodyid", "sms_pattern_args"):
        cfg[k] = s.get(k, cfg.get(k))
    return cfg


def send_for_lead(cfg: Dict[str, Any], lead: Dict[str, Any],
                  template: str, http_post=None) -> Dict[str, Any]:
    """ارسال همان قالب آماده‌شده به شمارهٔ همین سرنخ — بدون شرط خودکار.

    اگر sms_use_pattern روشن باشد از پترن (خط خدماتی) می‌فرستد؛
    وگرنه از SendSMS با خط اختصاصی.
    """
    ready, why = sms_ready(cfg)
    if not ready:
        return {"ok": False, "message": why}
    phone = normalize_ir_phone(lead.get("phone") or "")
    if not (phone.startswith("09") and len(phone) == 11):
        return {"ok": False, "message": f"شماره نامعتبر: {lead.get('phone')}"}
    user = cfg.get("sms_username") or ""
    pwd = cfg.get("sms_password") or cfg.get("sms_api_key") or ""
    if cfg.get("sms_use_pattern"):
        args = build_pattern_args(cfg, lead)
        return send_melipayamak_pattern(
            user, pwd, phone, (cfg.get("sms_pattern_bodyid") or "").strip(),
            args, http_post=http_post)
    text = compose_sms(template, lead)
    return send_melipayamak(
        user, pwd, phone, (cfg.get("sms_line_number") or "").strip(),
        text, http_post=http_post)


def maybe_send_for_lead(cfg: Dict[str, Any], lead: Dict[str, Any],
                        template: str, http_post=None) -> Optional[Dict[str, Any]]:
    """اگر ارسال خودکار روشن باشد، همان لحظه پیامک می‌زند."""
    if not cfg.get("sms_auto_on_new"):
        return None
    return send_for_lead(cfg, lead, template, http_post=http_post)
