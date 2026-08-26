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
        body: Any = {}
        try:
            body = r.json() or {}
        except Exception:
            body = {}
        if r.status_code == 200 and (not isinstance(body, dict) or body.get("ok") is not False):
            _set_chan(_LAST_BALE, ok=True, configured=True, path=BALE_API,
                      message="بله وصل شد")
            return r
        desc = ""
        if isinstance(body, dict):
            desc = str(body.get("description") or body)[:160]
        _set_chan(_LAST_BALE, ok=False, configured=True, path=BALE_API,
                  message=f"بله HTTP {r.status_code}: {desc}")
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
        body: Any = {}
        try:
            body = r.json() or {}
        except Exception:
            body = {}
        status = ""
        if isinstance(body, dict):
            status = str(body.get("status") or "")
        if r.status_code == 200 and str(status).upper() not in ("ERROR", "FAIL", "FALSE"):
            _set_chan(_LAST_RUBIKA, ok=True, configured=True, path=RUBIKA_API,
                      message="روبیکا وصل شد")
            return r
        _set_chan(_LAST_RUBIKA, ok=False, configured=True, path=RUBIKA_API,
                  message=f"روبیکا HTTP {r.status_code}: {str(body)[:160]}")
    except Exception as e:
        _set_chan(_LAST_RUBIKA, ok=False, configured=True,
                  message=f"{type(e).__name__}: {str(e)[:160]}")
    return None


def send_bale(cfg: Optional[Dict[str, Any]], text: str,
              extra: Optional[Dict[str, Any]] = None) -> bool:
    """API رسمی بله: https://tapi.bale.ai/bot<token>/sendMessage"""
    n = telegram_notify_cfg(cfg)
    chat = (n.get("bale_chat_id") or "").strip()
    if not bale_configured(cfg):
        _set_chan(_LAST_BALE, ok=False, configured=False,
                  message="توکن یا Chat ID بله نیست یا تیک استفاده خاموش است")
        return False
    payload: Dict[str, Any] = {"chat_id": chat, "text": text}
    if extra:
        payload.update(extra)
    return bale_request(cfg, "sendMessage", json=payload, timeout=12) is not None


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
            return {"ok": False, "channel": ch, **bale_last(),
                    "message": bale_last().get("message") or "بله پاسخ نداد"}
        if not (n.get("bale_chat_id") or "").strip():
            return {"ok": False, "channel": ch,
                    "message": "توکن معتبر است — شناسه گفتگو بله را بگذارید"}
        ok = send_bale(cfg, hello, extra={"reply_markup": REPLY_KEYBOARD})
        return {"ok": ok, "channel": ch, **bale_last(),
                "message": "ارتباط با بله برقرار شد — پیام آزمایشی فرستاده شد"
                if ok else (bale_last().get("message") or "ارسال نشد")}
    if ch == "rubika":
        n = telegram_notify_cfg(cfg)
        if not (n.get("rubika_bot_token") or "").strip():
            return {"ok": False, "channel": ch, "message": "توکن روبیکا را بگذارید"}
        r = rubika_request(cfg, "getMe", json={}, timeout=12)
        if r is None:
            return {"ok": False, "channel": ch, **rubika_last(),
                    "message": rubika_last().get("message") or "روبیکا پاسخ نداد"}
        if not (n.get("rubika_chat_id") or "").strip():
            return {"ok": False, "channel": ch,
                    "message": "توکن معتبر است — شناسه گفتگو روبیکا را بگذارید"}
        ok = send_rubika(cfg, hello, extra={
            "chat_keypad_type": "New", "chat_keypad": RUBIKA_CHAT_KEYPAD})
        return {"ok": ok, "channel": ch, **rubika_last(),
                "message": "ارتباط با روبیکا برقرار شد — پیام آزمایشی فرستاده شد"
                if ok else (rubika_last().get("message") or "ارسال نشد")}
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
