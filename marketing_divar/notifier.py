# -*- coding: utf-8 -*-
"""اعلان‌ها — کنسول + اختیاری تلگرام / بله / روبیکا طبق API رسمی هر پلتفرم."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

_LAST_TG: Dict[str, Any] = {
    "ok": False, "configured": False, "path": "",
    "message": "تلگرام پیکربندی نشده", "at": "",
}
_LAST_BALE: Dict[str, Any] = {
    "ok": False, "configured": False, "path": "",
    "message": "بله پیکربندی نشده", "at": "",
}
_LAST_RUBIKA: Dict[str, Any] = {
    "ok": False, "configured": False, "path": "",
    "message": "روبیکا پیکربندی نشده", "at": "",
}

BALE_API = "https://tapi.bale.ai"
RUBIKA_API = "https://botapi.rubika.ir/v3"


def telegram_last() -> Dict[str, Any]:
    return dict(_LAST_TG)


def _set_last(**kw: Any) -> None:
    _LAST_TG.update(kw)
    _LAST_TG["at"] = time.strftime("%Y-%m-%d %H:%M:%S")


def telegram_notify_cfg(cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return ((cfg or {}).get("notify") or {})


def telegram_bases(cfg: Optional[Dict[str, Any]]) -> List[str]:
    """مسیرهای Bot API: سفارشی کاربر اول، بعد api.telegram.org."""
    n = telegram_notify_cfg(cfg)
    custom = (n.get("telegram_api_base") or "").strip().rstrip("/")
    out: List[str] = []
    if custom:
        out.append(custom)
    out.append("https://api.telegram.org")
    seen, uniq = set(), []
    for b in out:
        if b and b not in seen:
            seen.add(b)
            uniq.append(b)
    return uniq


def telegram_proxy_tries(cfg: Optional[Dict[str, Any]]) -> List[Optional[Dict[str, str]]]:
    n = telegram_notify_cfg(cfg)
    p = (n.get("telegram_proxy") or "").strip()
    if not p:
        return [None]
    return [{"http": p, "https": p}, None]


def _flag_on(n: Dict[str, Any], key: str) -> bool:
    if key not in n:
        return True
    return bool(n.get(key))


def telegram_configured(cfg: Optional[Dict[str, Any]]) -> bool:
    n = telegram_notify_cfg(cfg)
    if not _flag_on(n, "telegram_enabled"):
        return False
    token = n.get("telegram_bot_token") or ""
    chat = n.get("telegram_chat_id") or ""
    return bool(token and chat and ":" in str(token))


def telegram_request(cfg: Optional[Dict[str, Any]], method: str, *,
                     json: Any = None, data: Any = None, files: Any = None,
                     params: Any = None, timeout: float = 15) -> Any:
    """یک متد Bot API را با چند مسیر/پروکسی امتحان می‌کند. None = همه ناموفق."""
    if requests is None:
        _set_last(ok=False, configured=False, path="", message="کتابخانه requests نیست")
        return None
    n = telegram_notify_cfg(cfg)
    token = n.get("telegram_bot_token") or ""
    if not token or ":" not in str(token):
        _set_last(ok=False, configured=False, path="", message="توکن ربات ذخیره نشده")
        return None
    last_err = "ارسال نشد"
    for base in telegram_bases(cfg):
        url = f"{base}/bot{token}/{method.lstrip('/')}"
        for proxies in telegram_proxy_tries(cfg):
            via = base + (" +proxy" if proxies else "")
            try:
                r = requests.post(url, json=json, data=data, files=files,
                                  params=params, timeout=timeout, proxies=proxies)
                if r.status_code == 200:
                    body: Any = {}
                    try:
                        body = r.json() or {}
                    except Exception:
                        body = {}
                    if isinstance(body, dict) and body.get("ok") is False:
                        last_err = f"تلگرام: {body.get('description') or body}"
                        continue
                    _set_last(ok=True, configured=True, path=via,
                              message="تلگرام وصل شد")
                    return r
                last_err = f"HTTP {r.status_code} از {via}"
            except Exception as e:
                last_err = f"{type(e).__name__} از {via}: {str(e)[:120]}"
    _set_last(ok=False, configured=True, path="",
              message="تلگرام فیلتر/قطع است — برنامه بدون ربات کار می‌کند. "
                      f"({last_err}) پروکسی یا آدرس Bot API سفارشی بگذارید.")
    return None


def send_telegram(cfg: Optional[Dict[str, Any]], text: str,
                  extra: Optional[Dict[str, Any]] = None) -> bool:
    n = telegram_notify_cfg(cfg)
    chat_id = n.get("telegram_chat_id")
    if not telegram_configured(cfg):
        _set_last(ok=False, configured=False, path="", message="توکن یا Chat ID نیست")
        return False
    payload: Dict[str, Any] = {"chat_id": chat_id, "text": text}
    if extra:
        payload.update(extra)
    r = telegram_request(cfg, "sendMessage", json=payload, timeout=12)
    return r is not None


def format_alert(message: str, account: str = "", problem: str = "",
                 operation: str = "", action: str = "") -> str:
    """متن اعلان ساخت‌یافته برای اپراتور."""
    lines = [message]
    if account:
        lines.append(f"اکانت: {account}")
    if problem:
        lines.append(f"مشکل: {problem}")
    if operation:
        lines.append(f"عملیات: {operation}")
    lines.append(f"زمان: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    if action:
        lines.append(f"اقدام لازم: {action}")
    return "\n".join(lines)


def bale_last() -> Dict[str, Any]:
    return dict(_LAST_BALE)


def rubika_last() -> Dict[str, Any]:
    return dict(_LAST_RUBIKA)


def _set_chan(store: Dict[str, Any], **kw: Any) -> None:
    store.update(kw)
    store["at"] = time.strftime("%Y-%m-%d %H:%M:%S")


def _ascii_digits(s: str) -> str:
    return (s or "").translate(str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


def _norm_chat_id(raw: Any, *, numeric: bool) -> Any:
    s = _ascii_digits(str(raw or "")).strip()
    if numeric and s.lstrip("-").isdigit():
        try:
            return int(s)
        except ValueError:
            return s
    return s


def _json_body(r: Any) -> Any:
    try:
        return r.json()
    except Exception:
        return None


def _bale_ok(body: Any) -> bool:
    """مستندات بله: هر پاسخ JSON فیلد بولی ok دارد؛ موفقیت فقط ok===true."""
    return isinstance(body, dict) and body.get("ok") is True


def _rubika_ok(body: Any) -> bool:
    """مستندات روبیکا: موفقیت با status=OK (یا data.message_id / data.bot)."""
    if not isinstance(body, dict):
        return False
    st = str(body.get("status") or "").strip().upper()
    if st in ("ERROR", "FAIL", "FALSE"):
        return False
    if st == "OK":
        return True
    data = body.get("data")
    if isinstance(data, dict) and (
            data.get("message_id") or data.get("bot")
            or data.get("bot_id") or data.get("updates") is not None):
        return True
    return bool(body.get("message_id") or body.get("bot"))


def _bale_err(body: Any, status_code: int) -> str:
    if isinstance(body, dict):
        desc = body.get("description")
        code = body.get("error_code")
        if desc:
            extra = f" ({code})" if code not in (None, "") else ""
            return f"بله: {desc}{extra}"
        return f"بله: پاسخ بدون ok=true (HTTP {status_code})"
    if body is None:
        return f"بله HTTP {status_code}: پاسخ JSON معتبر نبود"
    return f"بله HTTP {status_code}"


def _rubika_err(body: Any, status_code: int) -> str:
    if isinstance(body, dict):
        st = body.get("status")
        det = body.get("status_det") or body.get("description")
        data = body.get("data")
        if st or det:
            return ("روبیکا: " + str(st or "ناموفق")
                    + (f" — {det}" if det else ""))[:200]
        if isinstance(data, dict) and (data.get("error") or data.get("message")):
            return f"روبیکا: {data.get('error') or data.get('message')}"
        return f"روبیکا: پاسخ بدون status=OK (HTTP {status_code})"
    if body is None:
        return f"روبیکا HTTP {status_code}: پاسخ JSON معتبر نبود"
    return f"روبیکا HTTP {status_code}"


def _chats_from_bale_updates(body: Any) -> List[Any]:
    ids: List[Any] = []
    if not isinstance(body, dict):
        return ids
    for upd in body.get("result") or []:
        if not isinstance(upd, dict):
            continue
        msg = upd.get("message") or upd.get("edited_message") or {}
        if not isinstance(msg, dict):
            continue
        chat = (msg.get("chat") or {}).get("id")
        if chat is not None and chat not in ids:
            ids.append(chat)
    return ids


def _chats_from_rubika_updates(body: Any) -> List[Any]:
    ids: List[Any] = []
    if not isinstance(body, dict):
        return ids
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    for upd in (data.get("updates") or body.get("updates") or []):
        if not isinstance(upd, dict):
            continue
        inner = upd.get("update") if isinstance(upd.get("update"), dict) else upd
        chat = inner.get("chat_id")
        if chat and chat not in ids:
            ids.append(chat)
    return ids


def bale_configured(cfg: Optional[Dict[str, Any]]) -> bool:
    n = telegram_notify_cfg(cfg)
    if not _flag_on(n, "bale_enabled"):
        return False
    return bool((n.get("bale_bot_token") or "").strip()
                and (n.get("bale_chat_id") or "").strip())


def rubika_configured(cfg: Optional[Dict[str, Any]]) -> bool:
    n = telegram_notify_cfg(cfg)
    if not _flag_on(n, "rubika_enabled"):
        return False
    return bool((n.get("rubika_bot_token") or "").strip()
                and (n.get("rubika_chat_id") or "").strip())


def bale_request(cfg: Optional[Dict[str, Any]], method: str, *,
                 json: Any = None, data: Any = None, files: Any = None,
                 params: Any = None, timeout: float = 15) -> Any:
    """API رسمی بله: https://tapi.bale.ai/bot<token>/METHOD_NAME"""
    if requests is None:
        _set_chan(_LAST_BALE, ok=False, configured=False, message="requests نیست")
        return None
    n = telegram_notify_cfg(cfg)
    token = (n.get("bale_bot_token") or "").strip()
    if not token:
        _set_chan(_LAST_BALE, ok=False, configured=False, message="توکن بله نیست")
        return None
    url = f"{BALE_API}/bot{token}/{method.lstrip('/')}"
    try:
        r = requests.post(url, json=json, data=data, files=files,
                          params=params, timeout=timeout)
        body = _json_body(r)
        if r.status_code == 200 and _bale_ok(body):
            _set_chan(_LAST_BALE, ok=True, configured=True, path=BALE_API,
                      message="بله وصل شد")
            return r
        _set_chan(_LAST_BALE, ok=False, configured=True, path=BALE_API,
                  message=_bale_err(body, r.status_code))
    except Exception as e:
        _set_chan(_LAST_BALE, ok=False, configured=True,
                  message=f"{type(e).__name__}: {str(e)[:160]}")
    return None


def rubika_request(cfg: Optional[Dict[str, Any]], method: str, *,
                   json: Any = None, timeout: float = 15) -> Any:
    """API رسمی روبیکا: POST https://botapi.rubika.ir/v3/{token}/{method}"""
    if requests is None:
        _set_chan(_LAST_RUBIKA, ok=False, configured=False, message="requests نیست")
        return None
    n = telegram_notify_cfg(cfg)
    token = (n.get("rubika_bot_token") or "").strip()
    if not token:
        _set_chan(_LAST_RUBIKA, ok=False, configured=False, message="توکن روبیکا نیست")
        return None
    url = f"{RUBIKA_API}/{token}/{method.lstrip('/')}"
    try:
        r = requests.post(url, json=json if json is not None else {},
                          headers={"Content-Type": "application/json"},
                          timeout=timeout)
        body = _json_body(r)
        if r.status_code == 200 and _rubika_ok(body):
            _set_chan(_LAST_RUBIKA, ok=True, configured=True, path=RUBIKA_API,
                      message="روبیکا وصل شد")
            return r
        _set_chan(_LAST_RUBIKA, ok=False, configured=True, path=RUBIKA_API,
                  message=_rubika_err(body, r.status_code))
    except Exception as e:
        _set_chan(_LAST_RUBIKA, ok=False, configured=True,
                  message=f"{type(e).__name__}: {str(e)[:160]}")
    return None


def send_bale(cfg: Optional[Dict[str, Any]], text: str,
              extra: Optional[Dict[str, Any]] = None) -> bool:
    """API رسمی بله: https://tapi.bale.ai/bot<token>/sendMessage"""
    n = telegram_notify_cfg(cfg)
    chat = _norm_chat_id(n.get("bale_chat_id"), numeric=True)
    if not bale_configured(cfg):
        _set_chan(_LAST_BALE, ok=False, configured=False,
                  message="توکن یا Chat ID بله نیست یا تیک استفاده خاموش است")
        return False
    payload: Dict[str, Any] = {"chat_id": chat, "text": text}
    if extra:
        payload.update(extra)
        payload["chat_id"] = chat
        payload["text"] = text
    if bale_request(cfg, "sendMessage", json=payload, timeout=12) is not None:
        return True
    if extra:
        return bale_request(
            cfg, "sendMessage",
            json={"chat_id": chat, "text": text}, timeout=12) is not None
    return False


def send_rubika(cfg: Optional[Dict[str, Any]], text: str,
                extra: Optional[Dict[str, Any]] = None) -> bool:
    """API رسمی روبیکا: POST https://botapi.rubika.ir/v3/{token}/sendMessage"""
    n = telegram_notify_cfg(cfg)
    chat = (n.get("rubika_chat_id") or "").strip()
    if not rubika_configured(cfg):
        _set_chan(_LAST_RUBIKA, ok=False, configured=False,
                  message="توکن یا Chat ID روبیکا نیست یا تیک استفاده خاموش است")
        return False
    payload: Dict[str, Any] = {"chat_id": chat, "text": text}
    if extra:
        payload.update(extra)
    return rubika_request(cfg, "sendMessage", json=payload, timeout=12) is not None


def test_channel(cfg: Optional[Dict[str, Any]], channel: str) -> Dict[str, Any]:
    """getMe + پیام «ارتباط برقرار شد» طبق مستندات همان پلتفرم."""
    from .telegram_bot import REPLY_KEYBOARD, RUBIKA_CHAT_KEYPAD
    ch = (channel or "").strip().lower()
    hello = ("ارتباط با مارکتینگ دیوار برقرار شد.\n"
             "دکمه‌های پایین ربات: گزارش امروز، همه شماره‌ها، "
             "آلارم مهم، خروجی اکسل.")
    if ch == "telegram":
        n = telegram_notify_cfg(cfg)
        if not (n.get("telegram_bot_token") or "").strip():
            return {"ok": False, "channel": ch, "message": "توکن تلگرام را بگذارید"}
        r = telegram_request(cfg, "getMe", timeout=12)
        if r is None:
            return {"ok": False, "channel": ch, **telegram_last(),
                    "message": telegram_last().get("message") or "تلگرام پاسخ نداد"}
        if not (n.get("telegram_chat_id") or "").strip():
            return {"ok": False, "channel": ch,
                    "message": "توکن معتبر است — شناسه گفتگو (Chat ID) را بگذارید"}
        ok = send_telegram(cfg, hello, extra={"reply_markup": REPLY_KEYBOARD})
        return {"ok": ok, "channel": ch, **telegram_last(),
                "message": "ارتباط با تلگرام برقرار شد — پیام آزمایشی فرستاده شد"
                if ok else (telegram_last().get("message") or "ارسال نشد")}
    if ch == "bale":
        n = telegram_notify_cfg(cfg)
        if not (n.get("bale_bot_token") or "").strip():
            return {"ok": False, "channel": ch, "message": "توکن بله را بگذارید"}
        r = bale_request(cfg, "getMe", timeout=12)
        if r is None:
            last = bale_last()
            return {"channel": ch, **last, "ok": False,
                    "message": last.get("message") or "بله پاسخ نداد"}
        if not (n.get("bale_chat_id") or "").strip():
            return {"ok": False, "channel": ch,
                    "message": "توکن معتبر است — شناسه گفتگو بله را بگذارید"}
        bot_id = None
        try:
            bot_id = ((_json_body(r) or {}).get("result") or {}).get("id")
        except Exception:
            bot_id = None
        chat = _norm_chat_id(n.get("bale_chat_id"), numeric=True)
        if bot_id is not None and str(chat) == str(bot_id):
            _set_chan(_LAST_BALE, ok=False, configured=True,
                      message="شناسه گفتگو نباید شناسهٔ خود بازو باشد")
            ok = False
        else:
            ok = send_bale(cfg, hello, extra={"reply_markup": REPLY_KEYBOARD})
        suggested = None
        if not ok:
            ur = bale_request(cfg, "getUpdates",
                              json={"timeout": 0, "limit": 20}, timeout=12)
            found = _chats_from_bale_updates(_json_body(ur) if ur else None)
            found = [c for c in found if bot_id is None or str(c) != str(bot_id)]
            if found:
                suggested = found[-1]
                cfg2 = dict(cfg or {})
                n2 = dict(telegram_notify_cfg(cfg))
                n2["bale_chat_id"] = str(suggested)
                cfg2["notify"] = n2
                ok = send_bale(cfg2, hello)
        last = bale_last()
        if ok and suggested is not None:
            msg = (f"پیام فرستاده شد. شناسه گفتگوی درست: {suggested} "
                   "— همین را ذخیره کنید (نه شناسهٔ بازو).")
        elif ok:
            msg = "ارتباط با بله برقرار شد — پیام آزمایشی فرستاده شد"
        else:
            msg = (last.get("message") or "ارسال نشد") + (
                " — بازو را استارت کنید و شناسهٔ خودتان را بگذارید"
                if "ok=true" in str(last.get("message") or "")
                else "")
        out = {"channel": ch, **last, "ok": ok, "message": msg}
        if suggested is not None:
            out["suggested_chat_id"] = str(suggested)
        return out
    if ch == "rubika":
        n = telegram_notify_cfg(cfg)
        if not (n.get("rubika_bot_token") or "").strip():
            return {"ok": False, "channel": ch, "message": "توکن روبیکا را بگذارید"}
        r = rubika_request(cfg, "getMe", json={}, timeout=12)
        if r is None:
            last = rubika_last()
            return {"channel": ch, **last, "ok": False,
                    "message": last.get("message") or "روبیکا پاسخ نداد"}
        if not (n.get("rubika_chat_id") or "").strip():
            return {"ok": False, "channel": ch,
                    "message": "توکن معتبر است — شناسه گفتگو روبیکا را بگذارید"}
        ok = send_rubika(cfg, hello, extra={
            "chat_keypad_type": "New", "chat_keypad": RUBIKA_CHAT_KEYPAD})
        suggested = None
        if not ok:
            ur = rubika_request(cfg, "getUpdates", json={"limit": 20}, timeout=12)
            found = _chats_from_rubika_updates(_json_body(ur) if ur else None)
            if found:
                suggested = found[-1]
                cfg2 = dict(cfg or {})
                n2 = dict(telegram_notify_cfg(cfg))
                n2["rubika_chat_id"] = str(suggested)
                cfg2["notify"] = n2
                ok = send_rubika(cfg2, hello)
        last = rubika_last()
        if ok and suggested is not None:
            msg = (f"پیام فرستاده شد. شناسه گفتگوی درست: {suggested} "
                   "— همین را در پنل ذخیره کنید.")
        elif ok:
            msg = "ارتباط با روبیکا برقرار شد — پیام آزمایشی فرستاده شد"
        else:
            msg = last.get("message") or "ارسال نشد"
        out = {"channel": ch, **last, "ok": ok, "message": msg}
        if suggested is not None:
            out["suggested_chat_id"] = str(suggested)
        return out
    return {"ok": False, "channel": ch, "message": "پلتفرم ناشناخته"}


def channels_status(cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    tg = telegram_last()
    tg["configured"] = telegram_configured(cfg)
    if not tg["configured"]:
        tg["message"] = "توکن/Chat ID تلگرام ذخیره نشده یا تیک استفاده خاموش است"
    bl = bale_last()
    bl["configured"] = bale_configured(cfg)
    if not bl["configured"]:
        bl["message"] = "توکن/Chat ID بله ذخیره نشده یا تیک استفاده خاموش است"
    rb = rubika_last()
    rb["configured"] = rubika_configured(cfg)
    if not rb["configured"]:
        rb["message"] = "توکن/Chat ID روبیکا ذخیره نشده یا تیک استفاده خاموش است"
    return {"telegram": tg, "bale": bl, "rubika": rb}


def notify_mobile_reply(cfg: Dict[str, Any], title: str, phone: str, reply_text: str, platform: str = "divar", city: str = "", keyword: str = "") -> None:
    """وقتی سرنخ موبایل جواب داد، در روبیکا + تلگرام + بله خبر بده — v4"""
    try:
        # تشخیص موبایل بودن
        kw_low = (keyword or "").lower()
        title_low = (title or "").lower()
        is_mobile = any(w in kw_low or w in title_low for w in ["موبایل", "گوشی", "آیفون", "iphone", "سامسونگ", "شیائومی", "mobile", "phone"])
        if not is_mobile and keyword:
            # اگر کلمه کلیدی موبایل است
            is_mobile = True
        
        from .telegram_bot import mobile_reply_alert_text
        alert = mobile_reply_alert_text(title=title, phone=phone, reply_text=reply_text, platform=platform, city=city)
        
        # اگر موبایل است، با اهمیت بالا در همه ربات‌ها بفرست
        if is_mobile:
            print(f"📱 [MOBILE REPLY] {alert}")
            # روبیکا اولویت
            if rubika_configured(cfg):
                if not send_rubika(cfg, alert):
                    print(f"[!] روبیکا موبایل reply نشد: {_LAST_RUBIKA.get('message')}")
            if telegram_configured(cfg):
                if not send_telegram(cfg, alert):
                    print(f"[!] تلگرام موبایل reply نشد: {_LAST_TG.get('message')}")
            if bale_configured(cfg):
                if not send_bale(cfg, alert):
                    print(f"[!] بله موبایل reply نشد: {_LAST_BALE.get('message')}")
        else:
            # غیر موبایل هم با اهمیت کمتر
            print(f"💬 [REPLY] {alert}")
            notify(cfg, alert, important=False)
    except Exception as e:
        print(f"[!] notify_mobile_reply error: {e}")
        try:
            notify(cfg, f"پاسخ جدید: {title} — {phone}: {reply_text[:100]}", important=False)
        except Exception:
            pass


def notify(cfg: Dict[str, Any], message: str, important: bool = True,
           account: str = "", problem: str = "", operation: str = "",
           action: str = "") -> None:
    """پیام مهم را به تلگرام + بله + روبیکا (هر کدام که تیک و وصل باشد) می‌فرستد."""
    prefix = "🚨" if important else "ℹ️"
    text = format_alert(message, account=account, problem=problem,
                        operation=operation, action=action)
    print(f"{prefix} {text}")
    payload = f"{prefix} {text}"
    if telegram_configured(cfg):
        if not send_telegram(cfg, payload):
            print(f"[!] اعلان تلگرام ارسال نشد: {_LAST_TG.get('message')}")
    if bale_configured(cfg):
        if not send_bale(cfg, payload):
            print(f"[!] اعلان بله ارسال نشد: {_LAST_BALE.get('message')}")
    if rubika_configured(cfg):
        if not send_rubika(cfg, payload):
            print(f"[!] اعلان روبیکا ارسال نشد: {_LAST_RUBIKA.get('message')}")
