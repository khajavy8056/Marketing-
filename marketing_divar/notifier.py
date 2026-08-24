# -*- coding: utf-8 -*-
"""اعلان‌ها — کنسول + اختیاری تلگرام (مثلاً برای کپچا/بلاک وقتی دور از سیستمید)."""

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


def telegram_configured(cfg: Optional[Dict[str, Any]]) -> bool:
    n = telegram_notify_cfg(cfg)
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
    return bool((n.get("bale_bot_token") or "").strip()
                and (n.get("bale_chat_id") or "").strip())


def rubika_configured(cfg: Optional[Dict[str, Any]]) -> bool:
    n = telegram_notify_cfg(cfg)
    return bool((n.get("rubika_bot_token") or "").strip()
                and (n.get("rubika_chat_id") or "").strip())


def send_bale(cfg: Optional[Dict[str, Any]], text: str) -> bool:
    """API رسمی بله: https://tapi.bale.ai/bot<token>/sendMessage"""
    if requests is None:
        _set_chan(_LAST_BALE, ok=False, configured=False, message="requests نیست")
        return False
    n = telegram_notify_cfg(cfg)
    token = (n.get("bale_bot_token") or "").strip()
    chat = (n.get("bale_chat_id") or "").strip()
    if not token or not chat:
        _set_chan(_LAST_BALE, ok=False, configured=False,
                  message="توکن یا Chat ID بله نیست")
        return False
    url = f"{BALE_API}/bot{token}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": chat, "text": text}, timeout=12)
        body = {}
        try:
            body = r.json() or {}
        except Exception:
            body = {}
        if r.status_code == 200 and body.get("ok") is not False:
            _set_chan(_LAST_BALE, ok=True, configured=True, path=BALE_API,
                      message="بله وصل شد")
            return True
        _set_chan(_LAST_BALE, ok=False, configured=True, path=BALE_API,
                  message=f"بله HTTP {r.status_code}: {str(body)[:120]}")
    except Exception as e:
        _set_chan(_LAST_BALE, ok=False, configured=True,
                  message=f"{type(e).__name__}: {str(e)[:120]}")
    return False


def send_rubika(cfg: Optional[Dict[str, Any]], text: str) -> bool:
    """API رسمی روبیکا: POST https://botapi.rubika.ir/v3/{token}/sendMessage"""
    if requests is None:
        _set_chan(_LAST_RUBIKA, ok=False, configured=False, message="requests نیست")
        return False
    n = telegram_notify_cfg(cfg)
    token = (n.get("rubika_bot_token") or "").strip()
    chat = (n.get("rubika_chat_id") or "").strip()
    if not token or not chat:
        _set_chan(_LAST_RUBIKA, ok=False, configured=False,
                  message="توکن یا Chat ID روبیکا نیست")
        return False
    url = f"{RUBIKA_API}/{token}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": chat, "text": text}, timeout=12)
        body: Any = {}
        try:
            body = r.json() or {}
        except Exception:
            body = {}
        status = ""
        if isinstance(body, dict):
            status = str(body.get("status") or body.get("ok") or "")
        if r.status_code == 200 and str(status).upper() not in ("ERROR", "FAIL", "FALSE"):
            _set_chan(_LAST_RUBIKA, ok=True, configured=True, path=RUBIKA_API,
                      message="روبیکا وصل شد")
            return True
        _set_chan(_LAST_RUBIKA, ok=False, configured=True, path=RUBIKA_API,
                  message=f"روبیکا HTTP {r.status_code}: {str(body)[:120]}")
    except Exception as e:
        _set_chan(_LAST_RUBIKA, ok=False, configured=True,
                  message=f"{type(e).__name__}: {str(e)[:120]}")
    return False


def channels_status(cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    tg = telegram_last()
    tg["configured"] = telegram_configured(cfg)
    if not tg["configured"]:
        tg["message"] = "توکن/Chat ID تلگرام ذخیره نشده"
    bl = bale_last()
    bl["configured"] = bale_configured(cfg)
    if not bl["configured"]:
        bl["message"] = "توکن/Chat ID بله ذخیره نشده"
    rb = rubika_last()
    rb["configured"] = rubika_configured(cfg)
    if not rb["configured"]:
        rb["message"] = "توکن/Chat ID روبیکا ذخیره نشده"
    return {"telegram": tg, "bale": bl, "rubika": rb}


def notify(cfg: Dict[str, Any], message: str, important: bool = True,
           account: str = "", problem: str = "", operation: str = "",
           action: str = "") -> None:
    """پیام مهم را به تلگرام + بله + روبیکا (هر کدام که وصل باشد) می‌فرستد."""
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
