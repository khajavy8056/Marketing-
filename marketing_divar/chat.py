# -*- coding: utf-8 -*-
"""ارسال چت برای آگهی فقط‌چت — قالب با متغیر تا متن‌ها یکسان نباشند.

پیش‌فرض خاموش. سقف روزانه و فاصله. هر شکست → requires_operator.
آگهی حذف‌شده خطا نمی‌ترکاند؛ status=removed ثبت می‌شود.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

from .messaging import build_message


def chat_ready(cfg: Dict[str, Any]) -> Tuple[bool, str]:
    if not cfg.get("chat_auto_on_new") and not cfg.get("chat_auto_on"):
        return False, "ارسال خودکار چت خاموش است"
    tpl = (cfg.get("chat_template") or "").strip()
    if tpl and "{title}" not in tpl:
        return False, "قالب چت باید {title} داشته باشد تا متن‌ها یکسان نباشند"
    return True, "آماده"


def compose_chat(template: str, lead: Dict[str, Any]) -> str:
    safe = {
        "title": lead.get("title") or "آگهی شما",
        "subtitle": lead.get("subtitle") or "",
        "url": lead.get("url") or "",
        "city": lead.get("city") or "",
        "keyword": lead.get("keyword") or "",
        "price": lead.get("price") or 0,
        "published_at": lead.get("published_at") or "",
        "platform": lead.get("platform") or "divar",
        "questions": lead.get("questions") or lead.get("hunter_questions") or "",
    }
    text = build_message(template or "{greeting}\nآگهی «{title}» را دیدم.\n{closing}", safe)
    if not (lead.get("title") or "").strip():
        return text
    # اگر قالب title نداشت، عنوان را ته پیام می‌چسبانیم تا ضد اسپم بماند
    if "{title}" not in (template or "") and (lead.get("title") or "") not in text:
        text = text.rstrip() + "\n(درباره: %s)" % (lead.get("title") or "")[:80]
    return text


def send_divar_chat(client: Any, token: str, text: str,
                    send_fn: Optional[Callable] = None) -> Dict[str, Any]:
    """best-effort. send_fn قابل تزریق برای تست.

    اگر client.send_chat نباشد مسیر Chromium (chat_browser) صدا می‌شود.
    """
    if not (token and text):
        return {"ok": False, "status": "error",
                "message": "توکن آگهی و متن پیام لازم است"}
    poster: Callable = send_fn
    if poster is None:
        if client is not None and hasattr(client, "send_chat"):
            poster = lambda c, t, m: c.send_chat(t, m)
        else:
            poster = None
    try:
        if poster is not None:
            res = poster(client, token, text)
        else:
            from .chat_browser import send_for_token
            res = send_for_token(token, text, client=client)
    except Exception as e:
        return {"ok": False, "status": "requires_operator",
                "message": "ارسال چت ناموفق — اپراتور ادامه دهد (%s: %s)"
                           % (type(e).__name__, e)}
    if not isinstance(res, dict):
        res = {"ok": bool(res),
               "status": "sent" if res else "requires_operator",
               "message": str(res)}
    status = res.get("status") or ("sent" if res.get("ok") else "requires_operator")
    if status in ("removed", "gone", "deleted"):
        return {"ok": False, "status": "removed",
                "message": res.get("message") or "آگهی یا چت حذف شده"}
    ok = bool(res.get("ok"))
    return {"ok": ok, "status": status,
            "message": str(res.get("message") or "")[:240],
            "thread_id": res.get("thread_id") or ""}


def maybe_send_chat_for_lead(cfg: Dict[str, Any], lead: Dict[str, Any],
                             template: str, client: Any,
                             send_fn: Optional[Callable] = None
                             ) -> Optional[Dict[str, Any]]:
    if not (cfg.get("chat_auto_on_new") or cfg.get("chat_auto_on")):
        return None
    token = lead.get("token") or ""
    if not token:
        return {"ok": False, "status": "error", "message": "توکن آگهی نیست"}
    text = compose_chat(template, lead)
    return send_divar_chat(client, token, text, send_fn=send_fn)
