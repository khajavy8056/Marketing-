# -*- coding: utf-8 -*-
"""سیستم رویداد تعاملی — مثل n8n هر اتفاق تریگر دارد و مدل واکنش نشان می‌دهد.

رویدادها:
- keyword_added: کاربر کلمه/دسته جدید اضافه کرد → مدل درک اضافه می‌کند
- listing_found: آگهی جدید منطبق پیدا شد → بررسی قیمت/معیوب/شکارچی
- contact_found: شماره استخراج شد → آماده پیامک + حافظه
- chat_only: فقط چت تشخیص داده شد → آماده چت خودکار
- reply_received: پاسخ چت/پیامک آمد → NLU تحلیل + شکارچی امتیاز دوباره
- hunter_pending: شکارچی جای خالی دارد → تولید سوال استعلام با مدل
- captcha_hit: کپچا خورد → اعلان + توقف همان اکانت، بقیه ادامه
- sms_sent / chat_sent: ارسال انجام شد → لاگ + حافظه

هر رویداد می‌تواند چند handler داشته باشد. مدل به عنوان یک handler ثبت می‌شود
و وظیفه خودش را می‌داند.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List

_EVENT_LOCK = threading.Lock()
_HANDLERS: Dict[str, List[Callable]] = {}
_LOG: List[Dict[str, Any]] = []
_MAX_LOG = 200


def on(event: str, fn: Callable[[Dict[str, Any]], None]) -> None:
    """ثبت واکنش برای یک رویداد."""
    with _EVENT_LOCK:
        _HANDLERS.setdefault(event, []).append(fn)


def emit(event: str, payload: Dict[str, Any] | None = None) -> None:
    """اتفاق افتاد — همه واکنش‌ها صدا زده می‌شوند (بی‌صدا خطا نمی‌اندازد)."""
    payload = dict(payload or {})
    payload["event"] = event
    payload["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with _EVENT_LOCK:
        _LOG.append(payload)
        if len(_LOG) > _MAX_LOG:
            _LOG[:] = _LOG[-_MAX_LOG:]
        handlers = list(_HANDLERS.get(event) or [])
        # wildcards
        handlers += list(_HANDLERS.get("*") or [])
    for fn in handlers:
        try:
            fn(payload)
        except Exception:
            pass


def recent(limit: int = 50) -> List[Dict[str, Any]]:
    with _EVENT_LOCK:
        return list(_LOG[-limit:])


def clear() -> None:
    with _EVENT_LOCK:
        _LOG.clear()


# --- هندلرهای پیش‌فرض مدل ---

def _default_handlers():
    """مدل وظیفه خودش را از لحظه نصب می‌داند — اینجا ثبت می‌شود."""

    def on_keyword_added(p: Dict[str, Any]):
        try:
            from .nlu_memory import remember_keyword
            remember_keyword(
                keyword=p.get("keyword") or "",
                category=p.get("category") or "",
                city=str(p.get("cities") or ""),
                extra=p.get("extra"),
            )
        except Exception:
            pass

    def on_listing_found(p: Dict[str, Any]):
        try:
            from .nlu_memory import remember_listing
            remember_listing(
                token=p.get("token") or "",
                category=p.get("category") or "",
                hunter_level=p.get("hunter_level") or "",
                price=int(p.get("price") or 0),
                is_defect=bool(p.get("is_defect")),
            )
        except Exception:
            pass

    def on_reply(p: Dict[str, Any]):
        try:
            from .nlu_memory import remember_reply
            remember_reply(
                token=p.get("token") or "",
                intent=p.get("intent") or "",
                confidence=float(p.get("confidence") or 0),
                text=p.get("text") or p.get("body") or "",
                slots=p.get("slots"),
            )
        except Exception:
            pass

    def on_contact(p: Dict[str, Any]):
        # شماره از کدام پلتفرم آمده — حافظه برای تحلیل بعدی
        try:
            from .nlu_memory import get_memory
            # فقط لاگ، یادگیری ضمنی
            pass
        except Exception:
            pass

    on("keyword_added", on_keyword_added)
    on("listing_found", on_listing_found)
    on("reply_received", on_reply)
    on("contact_found", on_contact)
    on("chat_only", on_contact)


# ثبت اولیه
_default_handlers()
