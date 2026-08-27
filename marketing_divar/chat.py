# -*- coding: utf-8 -*-
"""ارسال خودکار پیام چت دیوار برای سرنخ‌های «فقط چت» (best-effort + fallback).

این ماژول دو جریان را پشتیبانی می‌کند:
  1) خودکار (opt-in): اگر «ارسال خودکار چت» روشن باشد، به محض اینکه آگهی
     «فقط چت» (phone_status='hidden') ثبت شود، متن قالب چت با اکانت لاگین‌شده
     به صاحب آگهی ارسال می‌شود.
  2) نیمه‌خودکار: جریان امن و توصیه‌شدهٔ مستندات — متن آماده می‌شود، چت در
     مرورگر باز می‌شود و انسان با یک کلیک ارسال می‌کند (ضد بن).

⚠️ هشدار (مطابق docs/feasibility-research.md و docs/challenges-and-countermeasures.md):
ارسال خودکار انبوه پیام در چت دیوار از مسیر غیررسمی پرریسک است و الگوی
«متن یکسان × تعداد زیاد» ساده‌ترین سیگنال اسپم است؛ می‌تواند اکانت و شماره را
بسوزاند. بنابراین:
- این قابلیت پیش‌فرض خاموش است (chat_auto_on_new=False).
- سقف روزانه (chat_auto_daily_limit) و تأخیر (chat_auto_delay_sec) سختگیرانه دارد.
- هر شکستی بلافاصله به مسیر نیمه‌خودکار برمی‌گردد (chat_status='requires_operator')
  و هرگز به‌صورت جعلی «ارسال موفق» ثبت نمی‌شود.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

from .messaging import build_message


def chat_ready(cfg: Dict[str, Any]) -> Tuple[bool, str]:
    """آیا ارسال خودکار چت آماده است؟ (نیازی به سرویس خارجی ندارد؛ فقط تیک)."""
    if not cfg.get("chat_auto_on_new"):
        return False, "ارسال خودکار چت خاموش است"
    return True, "آماده"


def compose_chat(template: str, lead: Dict[str, Any]) -> str:
    """متن شخصی‌سازی‌شدهٔ چت را با اطلاعات همان آگهی می‌سازد (ضد اسپم)."""
    safe = {"title": lead.get("title") or "آگهی شما",
            "subtitle": lead.get("subtitle") or "",
            "url": lead.get("url") or "",
            "city": lead.get("city") or "",
            "keyword": lead.get("keyword") or "",
            "price": lead.get("price") or 0,
            "published_at": lead.get("published_at") or ""}
    return build_message(template or "سلام، آگهی «{title}» را دیدم.", safe)


def send_divar_chat(client: Any, token: str, text: str,
                    send_fn: Optional[Callable] = None) -> Dict[str, Any]:
    """ارسال یک پیام چت به صاحب آگهی با اکانت لاگین‌شده (best-effort).

    ``send_fn`` قابل تزریق برای تست: ``(client, token, text) -> Dict``.

    خروجی همیشه dict با کلیدهای ``ok`` / ``status`` / ``message`` است. اگر ارسال
    قطعی نباشد ``status='requires_operator'`` برمی‌گردد تا اپراتورِ نیمه‌خودکار
    ادامه دهد — هرگز «ارسال موفق» جعلی ثبت نمی‌شود.
    """
    if not (token and text):
        return {"ok": False, "status": "error",
                "message": "توکن آگهی و متن پیام لازم است"}
    poster: Callable = send_fn
    if poster is None:
        poster = lambda c, t, m: c.send_chat(t, m)
    try:
        res = poster(client, token, text)
    except Exception as e:  # noqa: BLE001 — هر خطا به مسیر اپراتور برمی‌گردد
        return {"ok": False, "status": "requires_operator",
                "message": f"ارسال چت ناموفق — اپراتور ادامه دهد "
                           f"({type(e).__name__}: {e})"}
    if not isinstance(res, dict):
        res = {"ok": bool(res),
               "status": "sent" if res else "requires_operator",
               "message": str(res)}
    ok = bool(res.get("ok"))
    status = res.get("status") or ("sent" if ok else "requires_operator")
    return {"ok": ok, "status": status,
            "message": str(res.get("message") or "")[:200]}


def maybe_send_chat_for_lead(cfg: Dict[str, Any], lead: Dict[str, Any],
                             template: str, client: Any,
                             send_fn: Optional[Callable] = None
                             ) -> Optional[Dict[str, Any]]:
    """اگر ارسال خودکار چت روشن باشد، همان لحظه می‌فرستد؛ وگرنه None."""
    if not cfg.get("chat_auto_on_new"):
        return None
    token = lead.get("token") or ""
    if not token:
        return {"ok": False, "status": "error", "message": "توکن آگهی نیست"}
    text = compose_chat(template, lead)
    return send_divar_chat(client, token, text, send_fn=send_fn)
