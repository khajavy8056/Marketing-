# -*- coding: utf-8 -*-
"""ذخیره و تزریق کامل سشن دیوار (نه فقط یک کوکی).

دیوار دو لایه احراز دارد:
  ۱) API شماره‌گیری: JWT در Authorization (Basic/Bearer) — همان token فایل سشن
  ۲) سایت divar.ir: SuperTokens — کوکی/هدر
     sAccessToken, sRefreshToken, sFrontToken, st-last-access-token-update
     + هدرهای st-access-token / front-token / st-refresh-token

اگر فقط token را به کوکی .divar.ir بچسبانیم، صفحهٔ وب مهمان می‌ماند.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ST_HEADER_TO_COOKIE = {
    "st-access-token": "sAccessToken",
    "st-refresh-token": "sRefreshToken",
    "front-token": "sFrontToken",
    "anti-csrf": "sAntiCsrf",
    "id-refresh-token": "sIdRefreshToken",
}

# کوکی‌هایی که سایت دیوار برای «لاگین‌شده» می‌خواند
SITE_COOKIE_NAMES = (
    "sAccessToken", "sRefreshToken", "sFrontToken", "sAntiCsrf",
    "sIdRefreshToken", "st-last-access-token-update", "token", "did",
)

COOKIE_URLS = (
    "https://divar.ir/",
    "https://www.divar.ir/",
    "https://api.divar.ir/",
)

COOKIE_DOMAINS = (".divar.ir", "divar.ir", ".api.divar.ir", "api.divar.ir")


def _http_only(name: str) -> bool:
    return name not in ("sFrontToken", "token", "st-last-access-token-update", "did")


def _rec(name: str, value: str, domain: str = ".divar.ir",
         path: str = "/", http_only: Optional[bool] = None) -> Dict[str, Any]:
    return {
        "name": str(name),
        "value": str(value),
        "domain": domain or ".divar.ir",
        "path": path or "/",
        "secure": True,
        "httpOnly": _http_only(name) if http_only is None else bool(http_only),
        "sameSite": "Lax",
    }


def absorb_response(r: Any) -> Dict[str, Any]:
    """از پاسخ HTTP لاگین، کوکی + هدر SuperTokens را برمی‌دارد."""
    cookies: List[Dict[str, Any]] = []
    headers_auth: Dict[str, str] = {}
    jar = getattr(r, "cookies", None)
    try:
        items = list(jar) if jar is not None else []
    except Exception:
        items = []
    try:
        if items and all(hasattr(c, "name") for c in items):
            for c in items:
                cookies.append(_rec(
                    c.name, getattr(c, "value", ""),
                    getattr(c, "domain", None) or ".divar.ir",
                    getattr(c, "path", None) or "/"))
        elif jar is not None and hasattr(jar, "items"):
            for k, v in jar.items():
                cookies.append(_rec(str(k), str(v)))
        elif items and all(isinstance(c, str) for c in items) and hasattr(jar, "__getitem__"):
            for name in items:
                cookies.append(_rec(str(name), str(jar[name])))
    except Exception:
        pass
    raw_headers = getattr(r, "headers", None)
    items: List[tuple] = []
    try:
        if raw_headers is None:
            items = []
        elif hasattr(raw_headers, "items"):
            items = list(raw_headers.items())
        else:
            items = list(raw_headers)
    except Exception:
        items = []
    set_cookies: List[str] = []
    try:
        if raw_headers is not None and hasattr(raw_headers, "get_all"):
            set_cookies = list(raw_headers.get_all("Set-Cookie") or [])
            set_cookies += list(raw_headers.get_all("set-cookie") or [])
        elif raw_headers is not None and hasattr(raw_headers, "getlist"):
            set_cookies = list(raw_headers.getlist("Set-Cookie") or [])
    except Exception:
        set_cookies = []
    for k, v in items:
        lk = str(k).lower()
        if lk in ST_HEADER_TO_COOKIE and v:
            headers_auth[lk] = str(v)
            cookies.append(_rec(ST_HEADER_TO_COOKIE[lk], str(v)))
        if lk == "set-cookie" and v and str(v) not in set_cookies:
            set_cookies.append(str(v))
        if lk == "st-last-access-token-update" and v:
            cookies.append(_rec("st-last-access-token-update", str(v),
                                http_only=False))
    for raw in set_cookies:
        parsed = _parse_one_set_cookie(raw)
        if parsed:
            cookies.append(parsed)
    # یکتا بر اساس name+domain
    seen = set()
    uniq: List[Dict[str, Any]] = []
    for c in cookies:
        if not c.get("name") or c.get("value") is None:
            continue
        key = (c["name"], c.get("domain") or "")
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    return {"cookies_full": uniq, "auth_headers": headers_auth}


def _parse_one_set_cookie(raw: str) -> Optional[Dict[str, Any]]:
    if not raw or "=" not in raw:
        return None
    first, *rest = raw.split(";")
    name, _, val = first.partition("=")
    name, val = name.strip(), val.strip()
    if not name:
        return None
    domain, path, http_only = ".divar.ir", "/", None
    for part in rest:
        p = part.strip()
        low = p.lower()
        if low.startswith("domain="):
            domain = p.split("=", 1)[1].strip() or domain
        elif low.startswith("path="):
            path = p.split("=", 1)[1].strip() or path
        elif low == "httponly":
            http_only = True
    return _rec(name, val, domain, path, http_only)


def merge_into_session_file(session_path: str, phone: str, token: str,
                            absorbed: Optional[Dict[str, Any]] = None) -> None:
    p = Path(session_path)
    data: Dict[str, Any] = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}
    jar = dict(data.get("cookies") or {})
    full = list(data.get("cookies_full") or [])
    headers = dict(data.get("auth_headers") or {})
    absorbed = absorbed or {}
    for c in absorbed.get("cookies_full") or []:
        if c.get("name") and c.get("value") is not None:
            jar[str(c["name"])] = str(c["value"])
            full.append(c)
    headers.update(absorbed.get("auth_headers") or {})
    if token:
        jar.setdefault("token", token)
        jar.setdefault("sAccessToken", token)
        if not any(c.get("name") == "sAccessToken" for c in full):
            full.append(_rec("sAccessToken", token))
        if not any(c.get("name") == "token" for c in full):
            full.append(_rec("token", token, http_only=False))
    seen_full = {}
    for c in full:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        seen_full[(c["name"], c.get("domain") or "")] = c
    full = list(seen_full.values())
    data.update({
        "phone": phone or data.get("phone") or "",
        "token": token or data.get("token") or "",
        "cookies": jar,
        "cookies_full": full,
        "auth_headers": headers,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        import os
        os.chmod(p, 0o600)
    except OSError:
        pass


SITE_PROOF_NAMES = ("sFrontToken", "sRefreshToken", "sAntiCsrf")
SITE_PROOF_HEADERS = ("front-token", "st-refresh-token")


def front_token_from_jwt(token: str) -> str:
    """sFrontToken دیوار = base64(JSON uid/ate/up) از خود JWT."""
    import base64
    payload: Dict[str, Any] = {}
    if token and token.count(".") >= 2:
        raw = token.split(".")[1]
        pad = "=" * (-len(raw) % 4)
        try:
            decoded = json.loads(base64.urlsafe_b64decode(raw + pad))
            if isinstance(decoded, dict):
                payload = decoded
        except Exception:
            payload = {}
    uid = str(payload.get("sub") or payload.get("uid") or payload.get("userId")
              or payload.get("user_id") or "divar")
    exp = payload.get("exp")
    try:
        ate = int(float(exp) * 1000) if exp else int(time.time() * 1000) + 86400000 * 30
    except (TypeError, ValueError):
        ate = int(time.time() * 1000) + 86400000 * 30
    blob = json.dumps({"uid": uid, "ate": ate, "up": payload}, separators=(",", ":"))
    return base64.b64encode(blob.encode("utf-8")).decode("ascii")


def ensure_site_cookies_from_token(session_path: str, token: str,
                                   phone: str = "") -> None:
    """اگر SuperTokens نیامد، از JWT معتبر همان کوکی‌های سایت را می‌سازیم."""
    if not token:
        return
    data = session_data(session_path)
    names = _cookie_names(data)
    headers = data.get("auth_headers") or {}
    extra_ck: List[Dict[str, Any]] = []
    extra_hd: Dict[str, str] = {}
    if "sAccessToken" not in names:
        extra_ck.append(_rec("sAccessToken", token))
    if "token" not in names:
        extra_ck.append(_rec("token", token, http_only=False))
    if "sFrontToken" not in names and not headers.get("front-token"):
        ft = front_token_from_jwt(token)
        extra_ck.append(_rec("sFrontToken", ft, http_only=False))
        extra_hd["front-token"] = ft
    if extra_ck or extra_hd:
        merge_into_session_file(
            session_path, phone or data.get("phone") or "", token,
            {"cookies_full": extra_ck, "auth_headers": extra_hd})


def _cookie_names(data: Dict[str, Any]) -> set:
    names = set()
    for k in (data.get("cookies") or {}):
        names.add(str(k))
    for c in data.get("cookies_full") or []:
        if isinstance(c, dict) and c.get("name"):
            names.add(str(c["name"]))
    return names


def session_data(session_path: str) -> Dict[str, Any]:
    p = Path(session_path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def session_is_complete(session_path: str) -> bool:
    """سشن سایت کامل است؟ فقط JWT برای صفحهٔ لاگین‌شده کافی نیست."""
    data = session_data(session_path)
    if not data.get("token"):
        return False
    names = _cookie_names(data)
    if any(n in names for n in SITE_PROOF_NAMES):
        return True
    headers = data.get("auth_headers") or {}
    if any(headers.get(h) for h in SITE_PROOF_HEADERS):
        return True
    return False


def cookies_for_browser(session_path: str) -> List[Dict[str, Any]]:
    """لیست کوکی برای CDP — فقط اگر سشن سایت کامل باشد."""
    if not session_is_complete(session_path):
        return []
    data = session_data(session_path)
    token = str(data.get("token") or "")
    by_name: Dict[str, str] = {}
    for c in data.get("cookies_full") or []:
        if isinstance(c, dict) and c.get("name") and c.get("value") is not None:
            by_name[str(c["name"])] = str(c["value"])
    for k, v in (data.get("cookies") or {}).items():
        by_name.setdefault(str(k), str(v))
    for hk, ckname in ST_HEADER_TO_COOKIE.items():
        v = (data.get("auth_headers") or {}).get(hk)
        if v:
            by_name.setdefault(ckname, str(v))
    if token:
        by_name.setdefault("token", token)
        by_name.setdefault("sAccessToken", token)
    out: List[Dict[str, Any]] = []
    seen = set()
    for name, value in by_name.items():
        for domain in COOKIE_DOMAINS:
            key = (name, domain)
            if key in seen:
                continue
            seen.add(key)
            rec = _rec(name, value, domain)
            rec["urls"] = list(COOKIE_URLS)
            out.append(rec)
    return out


def localstorage_script(session_path: str) -> str:
    """قبل از بارگذاری دیوار در document اجرا می‌شود."""
    p = Path(session_path)
    token = ""
    front = ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        token = str(data.get("token") or (data.get("cookies") or {}).get("sAccessToken") or "")
        front = str((data.get("cookies") or {}).get("sFrontToken")
                    or (data.get("auth_headers") or {}).get("front-token") or "")
    except Exception:
        token = ""
    token_js = json.dumps(token)
    front_js = json.dumps(front)
    return (
        "(function(){try{"
        f"var t={token_js}, f={front_js};"
        "if(t){localStorage.setItem('token', t); sessionStorage.setItem('token', t);}"
        "if(f){localStorage.setItem('sFrontToken', f);}"
        "}catch(e){}})();"
    )


def cdp_cookie_params(ck: Dict[str, Any]) -> List[Dict[str, Any]]:
    """پارامتر Network.setCookie — با url (قابل‌اعتمادتر از domain تنها)."""
    name, value = ck.get("name"), ck.get("value")
    if not name or value is None:
        return []
    http_only = bool(ck.get("httpOnly", _http_only(str(name))))
    path = ck.get("path") or "/"
    out = []
    for url in ck.get("urls") or COOKIE_URLS:
        out.append({
            "name": str(name), "value": str(value),
            "url": url, "path": path,
            "secure": True, "httpOnly": http_only,
            "sameSite": "Lax",
        })
    return out
