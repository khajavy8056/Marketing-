# -*- coding: utf-8 -*-
"""کلاینت ارتباط با دیوار (غیررسمی) — جستجو، لاگین OTP، دریافت شماره.

نکات ضد بلاک:
- همه درخواست‌ها از RateLimiter عبور می‌کنند (تاخیر انسانی‌گونه).
- نشانه‌های بلاک/کپچا (403/429 یا محتوای captcha) → DivarBlockedError با جزئیات خام.
- اجرای این ماژول باید از IP ایران باشد.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from .rate import RateLimiter
from .logging_util import log as _log

# ═══════════════════════════ ترابری‌های چند-مسیری ═══════════════════════════
# هر مسیر در شرایطی جواب می‌دهد؛ _fetch به‌ترتیب امتحان می‌کند و مسیر برنده
# را به‌خاطر می‌سپارد (sticky). هدف: «حداقل یکی در هر شرایطی کار کند».
#   requests          → با پروکسی سیستم (اگر VPN درست کار کند)
#   requests-direct   → requests بدون پروکسی (درست برای IP ایران)
#   httpx-direct      → موتور دیگر HTTP بدون پروکسی
#   urllib-direct     → آخرین لایه استاندارد کتابخانه، بدون پروکسی

class _UrllibResp:
    """پاسخ urllib را شبیه requests.Response می‌کند (status_code/json/text)."""

    def __init__(self, code: int, body: bytes, headers=None):
        self.status_code = code
        self._body = body
        self.text = body.decode("utf-8", errors="replace")
        self.headers = headers or {}
        self.cookies = []

    def json(self):
        return json.loads(self._body or b"{}")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")


class _Transport:
    name = "?"

    def request(self, method: str, url: str, **kw):  # pragma: no cover
        raise NotImplementedError


class _RequestsEnvTransport(_Transport):
    """۱) requests با تنظیمات محیط/پروکسی سیستم."""
    name = "requests"

    def __init__(self, client: "DivarClient"):
        self.c = client

    def request(self, method, url, **kw):
        fn = self.c.http.get if method.upper() == "GET" else self.c.http.post
        return fn(url, **kw)


class _RequestsDirectTransport(_Transport):
    """۲) requests بدون پروکسی — مسیر درست برای کاربر داخل ایران."""
    name = "requests-direct"

    def __init__(self, client: "DivarClient"):
        self.c = client
        self._sess = None

    def _session(self):
        if self._sess is None:
            self._sess = requests.Session()
            self._sess.trust_env = False
        self._sess.headers.update(self.c.http.headers)
        for ck in self.c.http.cookies:
            self._sess.cookies.set(ck.name, ck.value)
        return self._sess

    def request(self, method, url, **kw):
        sess = self._session()
        fn = sess.get if method.upper() == "GET" else sess.post
        r = fn(url, **kw)
        try:
            for ck in sess.cookies:
                self.c.http.cookies.set(ck.name, ck.value)
        except Exception:
            pass
        return r


class _HttpxDirectTransport(_Transport):
    """۳) موتور httpx بدون پروکسی — موتور TCP/TLS متفاوت."""
    name = "httpx-direct"

    def __init__(self, client: "DivarClient"):
        self.c = client

    def request(self, method, url, **kw):
        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx نصب نیست")
        headers = dict(self.c.http.headers)
        headers.update(kw.get("headers") or {})
        cookie_bits = [headers["Cookie"]] if headers.get("Cookie") else []
        for ck in self.c.http.cookies:
            cookie_bits.append(f"{ck.name}={ck.value}")
        if cookie_bits:
            headers["Cookie"] = "; ".join(cookie_bits)
        timeout = kw.get("timeout", 25)
        with httpx.Client(verify=True, trust_env=False, timeout=timeout) as hc:
            if method.upper() == "GET":
                return hc.get(url, headers=headers,
                              params=kw.get("params"), timeout=timeout)
            return hc.post(url, headers=headers,
                           json=kw.get("json"), timeout=timeout)


class _UrllibDirectTransport(_Transport):
    """۴) urllib بدون هیچ پروکسی — آخرین لایهٔ نجات."""
    name = "urllib-direct"

    def __init__(self, client: "DivarClient"):
        self.c = client

    def request(self, method, url, **kw):
        import urllib.error
        import urllib.request
        import urllib.parse
        if kw.get("params"):
            url = url + "?" + urllib.parse.urlencode(kw["params"])
        data = None
        headers = {"User-Agent": str(self.c.http.headers.get("User-Agent", "")),
                   "Accept": "application/json"}
        headers.update(kw.get("headers") or {})
        if kw.get("json") is not None:
            data = json.dumps(kw["json"]).encode()
            headers.setdefault("Content-Type", "application/json")
        for ck in self.c.http.cookies:
            headers["Cookie"] = headers.get("Cookie", "") + f"; {ck.name}={ck.value}"
        if self.c.token and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {self.c.token}"
        req = urllib.request.Request(url, data=data, headers=headers,
                                     method=method.upper())
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}))  # بدون پروکسی
        try:
            with opener.open(req, timeout=kw.get("timeout", 25)) as resp:
                return _UrllibResp(resp.status, resp.read(), resp.headers)
        except urllib.error.HTTPError as e:
            return _UrllibResp(e.code, e.read() or b"", getattr(e, "headers", None))


def default_base() -> str:
    """آدرس پایه API — با متغیر DIVAR_BASE_URL قابل تغییر (برای تست با شبیه‌ساز)."""
    import os
    return os.environ.get("DIVAR_BASE_URL", "https://api.divar.ir")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

from .cities import CITIES as _CITIES, slug_of as _slug_of

CITY_SLUGS = {c["id"]: c["slug"] for c in _CITIES if c["slug"]}
CITY_SLUGS.update({str(k): v for k, v in list(CITY_SLUGS.items())})


def city_slug(cities: Optional[List[Any]]) -> str:
    """اسلاگ شهر برای HTML سایت؛ بدون شهر = iran."""
    if not cities:
        return "iran"
    return _slug_of(cities[0])


def _cookie_value(jar, name: str) -> str:
    """RequestsCookieJar با چند دامنه برای یک نام، .get را می‌ترکاند."""
    try:
        v = jar.get(name)
        return str(v) if v else ""
    except Exception:
        pass
    try:
        for c in jar:
            if getattr(c, "name", None) == name:
                return str(getattr(c, "value", "") or "")
    except Exception:
        pass
    return ""


HIDDEN_MARKER = "شماره مخفی شده است"
MOBILE_MARKER = "موبایل"          # عنوان ویجت شماره در پاسخ v2
HIDDEN_MARKER_V2 = "مخفی"         # عنوان ویجت شماره مخفی در v2

# ارقام فارسی/عربی → انگلیسی (دیوار گاهی ۰۹۱۲... می‌فرستد)
_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_phone(raw: Any) -> Optional[str]:
    """پاک‌سازی شماره: ارقام فارسی، فاصله، +98 → 09xxxxxxxxx"""
    if raw is None:
        return None
    t = str(raw).translate(_DIGIT_MAP).strip().replace(" ", "").replace("-", "")
    if not t or not any(c.isdigit() for c in t):
        return None
    if t.startswith("+98"):
        t = "0" + t[3:]
    elif t.startswith("98") and len(t) == 12:
        t = "0" + t[2:]
    if not t.startswith("0"):
        t = "0" + t
    return t if t.isdigit() and len(t) == 11 else t


def _phone_e164(phone: str) -> str:
    """SuperTokens اغلب +98xxxxxxxxxx می‌خواهد."""
    p = str(phone or "").strip()
    if p.startswith("09") and len(p) == 11 and p.isdigit():
        return "+98" + p[1:]
    return p


_HIDDEN_TITLES = ("مخفی", "شماره مخفی", "فقط چت", "از طریق چت")


def _walk_phone(obj: Any, depth: int = 0) -> Optional[str]:
    if depth > 6 or obj is None:
        return None
    if isinstance(obj, (str, int)):
        p = normalize_phone(obj)
        if p and str(p).startswith("09") and len(str(p)) == 11:
            return p
        return None
    if isinstance(obj, dict):
        for k in ("phone", "phone_number", "value", "mobile"):
            p = normalize_phone(obj.get(k))
            if p and str(p).startswith("09") and len(str(p)) == 11:
                return p
        for v in obj.values():
            p = _walk_phone(v, depth + 1)
            if p:
                return p
    elif isinstance(obj, list):
        for item in obj:
            p = _walk_phone(item, depth + 1)
            if p:
                return p
    return None


def classify_contact_widgets(widgets: Any) -> Dict[str, Any]:
    """شماره پیدا شد / صریحاً مخفی / هنوز معلوم نیست (error → صف شماره)."""
    if not isinstance(widgets, list) or not widgets:
        return {"status": "error", "message": "پاسخ تماس خالی بود — در صف شماره ماند"}
    saw_hidden = False
    for w in widgets:
        d = (w or {}).get("data") if isinstance(w, dict) else {}
        if not isinstance(d, dict):
            d = {}
        title = str(d.get("title") or "")
        phone = _walk_phone(d) or _walk_phone(w)
        if phone:
            return {"status": "found", "phone": phone}
        if any(m in title for m in _HIDDEN_TITLES) or title == HIDDEN_MARKER:
            saw_hidden = True
    if saw_hidden:
        return {"status": "hidden", "message": "explicit_hidden"}
    return {"status": "error", "message": "شماره در پاسخ نبود — در صف شماره ماند"}


# نشانه‌های واقعی کپچا — «challenge» به‌تنهایی در HTML عادی دیوار هم هست
CAPTCHA_MARKERS = ("captcha_required", "captcha-required", "arkose",
                   "hcaptcha", "recaptcha", "کپچا")


def _safe_json(r: Any) -> Any:
    try:
        return r.json()
    except Exception:
        return None


def _extract_otp_device(obj: Any, depth: int = 0) -> Dict[str, str]:
    """deviceId / preAuthSessionId را از هر شکل پاسخ SuperTokens برمی‌دارد."""
    out = {"deviceId": "", "preAuthSessionId": "", "flowType": ""}
    if depth > 6 or obj is None:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = str(k).lower().replace("_", "")
            if isinstance(v, str) and v.strip():
                if lk == "deviceid" and not out["deviceId"]:
                    out["deviceId"] = v.strip()
                elif lk == "preauthsessionid" and not out["preAuthSessionId"]:
                    out["preAuthSessionId"] = v.strip()
                elif lk == "flowtype" and not out["flowType"]:
                    out["flowType"] = v.strip()
            elif isinstance(v, dict):
                nested = _extract_otp_device(v, depth + 1)
                out["deviceId"] = out["deviceId"] or nested["deviceId"]
                out["preAuthSessionId"] = out["preAuthSessionId"] or nested["preAuthSessionId"]
                out["flowType"] = out["flowType"] or nested["flowType"]
            elif isinstance(v, list):
                for item in v[:8]:
                    nested = _extract_otp_device(item, depth + 1)
                    out["deviceId"] = out["deviceId"] or nested["deviceId"]
                    out["preAuthSessionId"] = out["preAuthSessionId"] or nested["preAuthSessionId"]
                    out["flowType"] = out["flowType"] or nested["flowType"]
    return out


def _token_from_payload(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    for k in ("token", "accessToken", "access_token", "sAccessToken"):
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    sess = data.get("session")
    if isinstance(sess, dict):
        at = sess.get("accessToken") or sess.get("token")
        if isinstance(at, dict) and isinstance(at.get("token"), str) and at["token"].strip():
            return at["token"].strip()
        if isinstance(at, str) and at.strip():
            return at.strip()
    user = data.get("user")
    if isinstance(user, dict):
        for k in ("token", "accessToken"):
            v = user.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""


class DivarAuthError(Exception):
    """توکن وجود ندارد، منقضی شده یا رد شده است."""


class DivarBlockedError(Exception):
    """دیوار ما را محدود/بلاک کرده یا کپچا خواسته — باید توقف و سرد شویم.

    detail: توضیح و خام‌ترین داده برای عیب‌یابی.
    """

    def __init__(self, message: str, status: int = 0, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body[:500]


def looks_like_captcha(text: str) -> bool:
    """فقط پاسخ‌های کوتاه/API؛ صفحهٔ HTML عادی دیوار پر از JS است."""
    t = (text or "").lower()
    if any(m in t for m in CAPTCHA_MARKERS):
        return True
    if len(t) < 2500 and any(m in t for m in ("captcha", "puzzle")):
        return True
    return False


_BLOCK_IMG = re.compile(
    r"(?:https?://[^\"'\\s<>]+?\.(?:png|jpe?g|gif|webp)(?:\?[^\"'\\s<>]*)?"
    r"|data:image/[a-zA-Z0-9+.-]+;base64,[A-Za-z0-9+/=]+)",
    re.I)


def parse_block_body(text: str) -> Dict[str, Any]:
    """اگر بدنهٔ ۴۰۳ تصویر/ویجت قابل‌نمایش داشته باشد برمی‌گرداند."""
    t = text or ""
    m = _BLOCK_IMG.search(t)
    img = m.group(0) if m else ""
    low = t.lower()
    has = bool(img) or any(x in low for x in (
        "arkose", "hcaptcha", "recaptcha", "funcaptcha"))
    return {"image_url": img, "has_widget": has}


def is_blocking_view(data: Any) -> bool:
    """پاسخ زنده ۱۴۰۵/۰۶: GET /v8/web-search فقط BLOCKING_VIEW می‌دهد (نسخه قدیمی)."""
    if not isinstance(data, dict):
        return False
    widgets = data.get("widget_list") or []
    if isinstance(widgets, list):
        for w in widgets:
            if isinstance(w, dict) and w.get("widget_type") == "BLOCKING_VIEW":
                return True
    return False


def extract_contact_uuid(data: Any) -> Optional[str]:
    """uuid تماس از posts-v2.

    شکل زنده ۱۴۰۵/۰۶:
      contact.action_log.server_side_info.info.contact_uuid
    شکل قدیمی/شبیه‌ساز:
      contact.contact_uuid
    """
    if not isinstance(data, dict):
        return None
    contact = data.get("contact")
    if isinstance(contact, dict):
        for key in ("contact_uuid", "contactUuid"):
            v = contact.get(key)
            if _looks_like_uuid(v):
                return str(v)
        found = _walk_contact_uuid(contact)
        if found:
            return found
    for key in ("contact_uuid", "contactUuid"):
        v = data.get(key)
        if _looks_like_uuid(v):
            return str(v)
    return _walk_contact_uuid(data)


def _looks_like_uuid(v: Any) -> bool:
    return isinstance(v, str) and len(v) >= 8


def _walk_contact_uuid(obj: Any, depth: int = 0) -> Optional[str]:
    if depth > 8 or obj is None:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("contact_uuid", "contactUuid") and _looks_like_uuid(v):
                return str(v)
            found = _walk_contact_uuid(v, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _walk_contact_uuid(item, depth + 1)
            if found:
                return found
    return None


class DivarClient:
    """کلاینت سشن‌دار دیوار با ذخیره‌سازی توکن لاگین."""

    def __init__(self, session_path: str = "data/session.json",
                 limiter: Optional[RateLimiter] = None,
                 base_url: Optional[str] = None):
        self.session_path = Path(session_path)
        self.base = base_url or default_base()
        self.http = requests.Session()
        self.http.headers.update({"User-Agent": UA, "Accept": "application/json"})
        self.token: Optional[str] = None
        self.limiter = limiter or RateLimiter()
        self._load_session()

    # ------------------------------------------------ درخواست چند-مسیری --
    def _transport_chain(self):
        """زنجیرهٔ مسیرها؛ مسیر برندهٔ قبلی اول می‌آید (sticky)."""
        if getattr(self, "_custom_transports", None) is not None:
            chain = list(self._custom_transports)
        else:
            chain = [_RequestsEnvTransport(self), _RequestsDirectTransport(self),
                     _HttpxDirectTransport(self), _UrllibDirectTransport(self)]
        w = getattr(self, "_winner", None)
        if w:
            chain.sort(key=lambda t: 0 if t.name == w else 1)  # برنده اول
        return chain

    def _fetch(self, method: str, url: str, **kw):
        """درخواست HTTP با ۴ مسیر پشت‌سرهم + لاگ دقیق هر تلاش.

        اگر مسیری خطای شبکه داد، مسیر بعدی امتحان می‌شود؛ اولین مسیر
        موفق به‌خاطر سپرده می‌شود (sticky) تا درخواست‌های بعدی سریع باشند.
        """
        last_err: Exception = RuntimeError("هیچ مسیر اتصالی امتحان نشد")
        for tr in self._transport_chain():
            t0 = time.time()
            try:
                r = tr.request(method, url, **kw)
                self._winner = tr.name
                self._absorb_auth(r)
                ms = int((time.time() - t0) * 1000)
                _log("info", f"⇄ {method} {url.split('?')[0][-60:]} → "
                             f"HTTP {r.status_code} ({ms}ms؛ مسیر: {tr.name})")
                return r
            except requests.exceptions.HTTPError:
                raise
            except Exception as e:
                last_err = e
                ms = int((time.time() - t0) * 1000)
                _log("warning", f"مسیر «{tr.name}» ناموفق ({ms}ms): "
                                f"{type(e).__name__}: {str(e)[:120]}")
        raise last_err

    # ------------------------------------------------------------- session --
    def _absorb_auth(self, r) -> None:
        """کوکی و هدر SuperTokens پاسخ را در سشن HTTP همین اکانت نگه می‌دارد."""
        from .auth_session import absorb_response
        bag = absorb_response(r)
        prev = getattr(self, "_last_absorbed", None) or {}
        merged_full = list(prev.get("cookies_full") or []) + list(bag.get("cookies_full") or [])
        merged_hdr = dict(prev.get("auth_headers") or {})
        merged_hdr.update(bag.get("auth_headers") or {})
        self._last_absorbed = {"cookies_full": merged_full, "auth_headers": merged_hdr}
        seen_names = set()
        for c in bag.get("cookies_full") or []:
            name = c.get("name")
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            try:
                self.http.cookies.set(name, c.get("value") or "")
            except Exception:
                pass

    def _load_session(self) -> None:
        if self.session_path.exists():
            try:
                data = json.loads(self.session_path.read_text(encoding="utf-8"))
                self.token = data.get("token")
                for k, v in (data.get("cookies") or {}).items():
                    self.http.cookies.set(k, v)
                for c in data.get("cookies_full") or []:
                    if isinstance(c, dict) and c.get("name"):
                        self.http.cookies.set(c["name"], c.get("value") or "")
            except Exception:
                self.token = None

    def _save_session(self, phone: str) -> None:
        from .auth_session import absorb_response, merge_into_session_file
        extra = dict(getattr(self, "_last_absorbed", None) or {})
        try:
            extra_http = absorb_response(type("R", (), {
                "cookies": self.http.cookies, "headers": {}})())
            extra = {
                "cookies_full": list(extra.get("cookies_full") or [])
                + list(extra_http.get("cookies_full") or []),
                "auth_headers": dict(extra.get("auth_headers") or {}),
            }
        except Exception:
            pass
        merge_into_session_file(str(self.session_path), phone, self.token or "", extra)

    def is_logged_in(self) -> bool:
        return bool(self.token)

    def reload_session(self) -> None:
        """خواندن مجدد توکن از دیسک (مثلاً بعد از لاگین مجدد از ترمینال دیگر)."""
        self._load_session()

    # --------------------------------------------------------------- login --
    def _otp_pending_path(self) -> Path:
        return self.session_path.parent / "otp_pending.json"

    def _st_headers(self) -> Dict[str, str]:
        return {"rid": "passwordless", "st-auth-mode": "cookie",
                "fdi-version": "1.17", "Content-Type": "application/json",
                "Accept": "application/json",
                "Origin": "https://divar.ir", "Referer": "https://divar.ir/"}

    def _save_otp_pending(self, phone: str, data: Any) -> Dict[str, str]:
        rec = {"phone": str(phone), "deviceId": "", "preAuthSessionId": "",
               "flowType": "", "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        rec.update(_extract_otp_device(data))
        p = self._otp_pending_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        return rec

    def _load_otp_pending(self, phone: str) -> Dict[str, str]:
        p = self._otp_pending_path()
        if not p.exists():
            return {}
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(rec, dict):
            return {}
        if rec.get("phone") and str(rec.get("phone")) != str(phone):
            return rec
        return rec

    def _clear_otp_pending(self) -> None:
        try:
            p = self._otp_pending_path()
            if p.exists():
                p.unlink()
        except OSError:
            pass

    def _merge_absorbed(self, bag: Dict[str, Any]) -> None:
        prev = getattr(self, "_last_absorbed", None) or {}
        self._last_absorbed = {
            "cookies_full": list(prev.get("cookies_full") or [])
            + list(bag.get("cookies_full") or []),
            "auth_headers": {**dict(prev.get("auth_headers") or {}),
                             **dict(bag.get("auth_headers") or {})},
        }
        seen = set()
        for c in bag.get("cookies_full") or []:
            name = c.get("name")
            if not name or name in seen:
                continue
            seen.add(name)
            try:
                self.http.cookies.set(name, c.get("value") or "")
            except Exception:
                pass

    def _apply_login_body(self, r) -> None:
        from .auth_session import absorb_login_json
        self._merge_absorbed(absorb_login_json(_safe_json(r)))

    def _st_consume_ok(self, r) -> bool:
        if r is None or getattr(r, "status_code", 0) not in (200, 201):
            return False
        data = _safe_json(r)
        if isinstance(data, dict):
            st = str(data.get("status") or "")
            if st in ("INCORRECT_USER_INPUT_CODE_ERROR",
                      "EXPIRED_USER_INPUT_CODE_ERROR",
                      "RESTART_FLOW_ERROR", "GENERAL_ERROR"):
                return False
        return True

    def _try_v5_confirm(self, phone: str, code: str) -> str:
        try:
            r = self._fetch("POST", f"{self.base}/v5/auth/confirm",
                            json={"phone": str(phone), "code": str(code)},
                            timeout=25)
        except Exception:
            return ""
        if r.status_code in (200, 201):
            return _token_from_payload(_safe_json(r)) or ""
        return ""

    def _finish_login(self, phone: str, token: str = "") -> str:
        """فقط توکن API. سشن سایت از مرورگر واقعی جمع می‌شود — اینجا جعل نمی‌شود."""
        if token:
            self.token = token
        if not self.token:
            self.token = (_cookie_value(self.http.cookies, "token") or "")
        self._save_session(phone)
        self._clear_otp_pending()
        return self.token or ""

    def request_otp(self, phone: str) -> bool:
        """گام ۱: همان مسیر قدیمی v5 — SuperTokens را اینجا صدا نمی‌زنیم (کد را می‌سوزاند)."""
        r = self._fetch("POST", f"{self.base}/v5/auth/authenticate",
                        json={"phone": str(phone)}, timeout=25)
        if r.status_code in (200, 201):
            self._save_otp_pending(phone, {})
            _log("info", "OTP v5 ارسال شد")
            return True
        if r.status_code in (403, 429) or looks_like_captcha(r.text):
            raise DivarBlockedError("درخواست کد محدود شد (شاید تلاش‌های زیاد OTP)",
                                    r.status_code, r.text)
        raise RuntimeError(
            f"ارسال کد ناموفق: HTTP {r.status_code} — {r.text[:150]}")

    def confirm_otp(self, phone: str, code: str) -> str:
        """گام ۲: تأیید کد v5 → JWT برای شماره‌گیری. سشن سایت جدا جمع می‌شود."""
        try:
            r = self._fetch("POST", f"{self.base}/v5/auth/confirm",
                            json={"phone": str(phone), "code": str(code)},
                            timeout=25)
        except requests.exceptions.RequestException as e:
            raise DivarAuthError(f"ارتباط برای تأیید کد قطع شد: {e}") from e
        if r.status_code in (200, 201):
            tok = _token_from_payload(_safe_json(r)) or ""
            if tok:
                return self._finish_login(phone, tok)
            raise DivarAuthError("کد قبول شد ولی توکن نیامد — دوباره کد بگیرید")
        raise DivarAuthError(
            f"کد نامعتبر یا منقضی (HTTP {r.status_code})")

    def login_interactive(self, phone: Optional[str] = None) -> None:
        """جریان کامل لاگین: شماره → کد پیامکی → ذخیره توکن."""
        if phone is None:
            phone = input("شماره موبایل (09xxxxxxxxx): ").strip()
        if not phone.startswith("09") or len(phone) != 11 or not phone.isdigit():
            raise ValueError("فرمت شماره درست نیست؛ باید 11 رقم و با 09 شروع شود")
        print("در حال ارسال کد تایید پیامکی… (اگر نرسید، بعد از ۲ دقیقه دوباره تلاش کنید)")
        self.request_otp(phone)
        code = input("کد ۶ رقمی دریافتی از پیامک دیوار: ").strip()
        self.confirm_otp(phone, code)
        print("✓ لاگین موفق؛ توکن در فایل سشن ذخیره شد")

    def _auth_headers(self) -> Dict[str, str]:
        if not self.token:
            raise DivarAuthError("ابتدا لاگین کنید (فرمان: login)")
        return {"Authorization": f"Basic {self.token}"}

    # ------------------------------------------------------------ درخواست‌ها --
    @staticmethod
    def _check_block(r: requests.Response) -> None:
        if r.status_code == 429:
            raise DivarBlockedError("محدودیت نرخ دیوار (429)", 429, r.text)
        if r.status_code == 403 and looks_like_captcha(r.text):
            raise DivarBlockedError("چالش کپچا فعال شد (403)", 403, r.text)
        if r.status_code == 403:
            raise DivarBlockedError(
                "دسترسی ممنوع (403) — اگر VPN/پروکسی روشن است خاموش کنید؛ "
                "دیوار فقط با IP ایران جواب می‌دهد", 403, r.text)

    def search(self, query: str, cities: Optional[List[int]] = None,
               page: int = 1, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """جستجوی کلمه‌کلیدی و/یا دستهٔ دیوار — چند مسیر تا یکی جواب بدهد.

        دسته همان اسلاگ عمومی /s/{شهر}/{دسته} است (موبایل، خودرو، …).
        """
        from .categories import normalize_slug
        cat = normalize_slug(category)
        self.limiter.wait("search")
        params: Dict[str, Any] = {}
        if query:
            params["q"] = query
        elif cat:
            params["sort"] = "sort_date"
        if cities:
            params["cities"] = ",".join(str(c) for c in cities)
        if page and page > 1:
            params["page"] = page
        api_path = f"{self.base}/v8/web-search/iran"
        if cat:
            city = city_slug(cities)
            api_path = f"{self.base}/v8/web-search/{city}/{cat}"
        try:
            r = self._fetch("GET", api_path,
                            params=params, timeout=25,
                            headers={"Accept-Language": "fa-IR,fa;q=0.9",
                                     "Referer": "https://divar.ir/"})
            self._check_block(r)
            if r.status_code in (401, 403, 451):
                raise DivarBlockedError(
                    f"دیوار جستجو را رد کرد (HTTP {r.status_code}) — اگر VPN/پروکسی "
                    "روشن است خاموش کنید؛ دیوار فقط با IP ایران جواب می‌دهد",
                    status=r.status_code)
            r.raise_for_status()
            data = r.json()
            if is_blocking_view(data):
                _log("warning", "API جستجو BLOCKING_VIEW داد (نسخه قدیمی) — مسیرهای بعدی")
            else:
                posts = self._extract_post_list(data)
                if posts:
                    return posts
                _log("warning", "API جستجو ۰ آگهی داد — مسیرهای بعدی")
        except DivarBlockedError as e:
            if e.status == 429:
                raise
            _log("warning", f"API جستجو محدود شد ({e}) — مسیرهای بعدی")
        except Exception as e:
            _log("warning", f"API جستجو ناموفق ({type(e).__name__}: {str(e)[:100]}) "
                            "— مسیرهای بعدی")
        try:
            posts = self._search_post_v8(query, cities, page, cat)
            if posts:
                return posts
        except DivarBlockedError as e:
            if e.status == 429:
                raise
            _log("warning", f"POST /v8/search محدود شد ({e}) — HTML سایت")
        except Exception as e:
            _log("warning", f"POST /v8/search ناموفق ({type(e).__name__}: {str(e)[:80]})")
        return self._search_html(query, cities, page, cat)

    # href نسبی + URL کامل + لینک مارک‌داون + توکن تکی /v/TOKEN
    _HTML_URL = re.compile(
        r"(?:https?://(?:www\.)?divar\.ir)?/v/([^\"'/\s?]+)/([A-Za-z0-9_-]{5,16})"
    )
    _HTML_TOKEN_ONLY = re.compile(
        r"(?:https?://(?:www\.)?divar\.ir)?/v/([A-Za-z][A-Za-z0-9_-]{4,15})(?=[\"'\s?#]|$)"
    )
    _HTML_JSON_TOKEN = re.compile(
        r'"token"\s*:\s*"([A-Za-z][A-Za-z0-9_-]{4,15})"'
    )
    _HTML_SKIP = frozenset({"chat", "rules", "about", "download", "help", "new",
                            "s", "entity", "assets"})

    @staticmethod
    def _parse_search_html(html: str) -> List[Dict[str, Any]]:
        """استخراج توکن + عنوان از HTML/مارک‌داون/JSON توکار صفحهٔ جستجو."""
        import urllib.parse as _up
        posts, seen = [], set()

        def _keep(token: str, title: str, slug: str = "") -> None:
            if not token or token in seen or token.lower() in DivarClient._HTML_SKIP:
                return
            if slug.startswith("s/") or slug in DivarClient._HTML_SKIP:
                return
            seen.add(token)
            posts.append({"token": token, "title": title or "—",
                          "subtitle": "",
                          "url": (f"https://divar.ir/v/{slug}/{token}" if slug
                                  else f"https://divar.ir/v/{token}")})

        for slug, token in DivarClient._HTML_URL.findall(html or ""):
            title = _up.unquote(slug).replace("-", " ").strip()
            _keep(token, title, slug)
        for token in DivarClient._HTML_TOKEN_ONLY.findall(html or ""):
            _keep(token, "")
        for token in DivarClient._HTML_JSON_TOKEN.findall(html or ""):
            _keep(token, "")
        DivarClient._enrich_html_prices(html or "", posts)
        return posts[:80]

    _HTML_OFFER_PRICE = re.compile(r'"price"\s*:\s*"?(\d{4,})"?' )

    @staticmethod
    def _enrich_html_prices(html: str, posts: List[Dict[str, Any]]) -> None:
        """قیمت JSON-LD نزدیک توکن (اسکیما دیوار معمولاً ریال است)."""
        from .pricing import parse_toman
        for p in posts:
            tok = p.get("token") or ""
            if not tok:
                continue
            i = html.find(tok)
            window = html[max(0, i - 500): i + 900] if i >= 0 else html[:2000]
            m = DivarClient._HTML_OFFER_PRICE.search(window)
            if m:
                rial = int(m.group(1))
                p["price"] = rial // 10 if rial >= 1000 else rial
                p["price_text"] = m.group(1)
                continue
            t = parse_toman(window)
            if t:
                p["price"] = t

    def _search_html(self, query: str, cities=None, page: int = 1,
                     category: str = ""):
        """جستجو از HTML سایت (راه نجات وقتی API خاموش/تغییرشکل‌داده است)."""
        host = "https://divar.ir"
        if self.base.startswith("http") and "divar.ir" not in self.base:
            host = self.base  # شبیه‌ساز تست
        city = city_slug(cities)
        url = f"{host}/s/{city}"
        if category:
            url = f"{host}/s/{city}/{category}"
        params: Dict[str, Any] = {}
        if query:
            params["q"] = query
        elif category:
            # لیست خود دسته، جدیدترین‌ها اول — مثل صفحهٔ دیوار
            params["sort"] = "sort_date"
        if page and page > 1:
            params["page"] = page
        r = self._fetch("GET", url, params=params, timeout=25,
                        headers={"Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                                 "Accept-Language": "fa-IR,fa;q=0.9"})
        if r.status_code in (403, 429):
            raise DivarBlockedError(
                f"HTML جستجو HTTP {r.status_code} داد — اگر VPN/پروکسی روشن است خاموش کنید؛ "
                "دیوار فقط با IP ایران جواب می‌دهد", r.status_code, r.text[:200])
        if r.status_code != 200:
            _log("warning", f"HTML جستجو HTTP {r.status_code} داد — بدون آگهی")
            return []
        posts = self._parse_search_html(r.text)
        _log("success" if posts else "warning",
             f"جستجوی HTML سایت: {len(posts)} آگهی پیدا شد" if posts
             else "جستجوی HTML سایت هم ۰ آگهی داد")
        return posts

    def _search_post_v8(self, query: str, cities=None, page: int = 1,
                        category: str = "") -> List[Dict[str, Any]]:
        """مسیر جایگزین جامعه: POST /v8/search/{شهر}. اگر شکل عوض شود، خالی برمی‌گردد."""
        city = city_slug(cities)
        url = f"{self.base}/v8/search/{city}"
        schema: Dict[str, Any] = {}
        if query:
            schema["query"] = query
        if category:
            schema["category"] = {"value": category}
        payload = {"city": city, "q": query or "", "page": page or 1,
                   "json_schema": schema or {"query": query or ""}}
        r = self._fetch("POST", url, json=payload, timeout=25)
        self._check_block(r)
        if r.status_code != 200:
            _log("warning", f"POST /v8/search HTTP {r.status_code}")
            return []
        data = r.json()
        if is_blocking_view(data):
            return []
        posts = self._extract_post_list(data)
        if posts:
            _log("success", f"جستجوی POST /v8/search: {len(posts)} آگهی")
        return posts

    @staticmethod
    def _extract_post_list(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        web_widgets = data.get("web_widgets") or {}
        raw = web_widgets.get("post_list") if isinstance(web_widgets, dict) else None
        posts: List[Dict[str, Any]] = []
        seen = set()

        from .pricing import parse_toman

        def _add(d: Dict[str, Any]) -> None:
            tok = d.get("token")
            if not tok and isinstance(d.get("action"), dict):
                tok = ((d.get("action") or {}).get("payload") or {}).get("token")
            if not tok or tok in seen:
                return
            seen.add(tok)
            price_blob = " ".join(str(x) for x in (
                d.get("middle_description_text"), d.get("bottom_description_text"),
                d.get("top_description_text"), d.get("title")) if x)
            posts.append({
                "token": tok,
                "title": d.get("title") or "",
                "subtitle": d.get("middle_description_text") or "",
                "top": d.get("top_description_text") or "",
                "bottom": d.get("bottom_description_text") or "",
                "has_chat": bool(d.get("has_chat", False)),
                "url": f"https://divar.ir/v/{tok}",
                "price": parse_toman(price_blob),
                "price_text": d.get("middle_description_text") or "",
            })

        for item in raw or []:
            _add((item or {}).get("data") or {})
        for item in data.get("widget_list") or []:
            if not isinstance(item, dict):
                continue
            if item.get("widget_type") == "BLOCKING_VIEW":
                continue
            _add(item.get("data") or {})
        return posts

    def get_post(self, token: str) -> Dict[str, Any]:
        """جزئیات کامل آگهی."""
        self.limiter.wait("search")
        r = self._fetch("GET", f"{self.base}/v8/posts-v2/web/{token}", timeout=25)
        self._check_block(r)
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------ phone 🔑 --
    def get_contact_uuid(self, token: str) -> Optional[str]:
        """گام ۱ فلوی v2: شناسه تماس از جزئیات آگهی (بدون لاگین)."""
        r = self._fetch("GET", f"{self.base}/v8/posts-v2/web/{token}", timeout=25)
        if r.status_code == 404:
            return None  # آگهی حذف شده
        if r.status_code != 200:
            return None
        try:
            return extract_contact_uuid(r.json())
        except ValueError:
            return None
    def get_phone(self, token: str) -> Dict[str, Any]:
        """دریافت شماره تماس آگهی (نیاز به لاگین).

        فلوی اصلی (v2 — مطابق رفتار فعلی دیوار):
          ۱) GET  /v8/posts-v2/web/{token}              → contact.contact_uuid
          ۲) POST /v8/postcontact/web/contact_info_v2/  → Authorization: Bearer
             payload={"contact_uuid": ...} → widget_list → «شمارهٔ موبایل» → value
        فلوی پشتیبان (v1 قدیمی): GET contact_info/{token} با Basic

        خروجی: {"status": "found"|"hidden"|"removed"|"error", ...}
        """
        auth = self._auth_headers()  # DivarAuthError اگر لاگین نیست
        if self.limiter:
            self.limiter.wait("phone")
        uuid = self.get_contact_uuid(token)
        if uuid is None:
            # آگهی حذف شده یا پاسخ نامعتبر — با v1 هم امتحان می‌کنیم
            return self._get_phone_v1(token)

        res = self._get_phone_v2(token, uuid, auth)
        if res.get("status") == "error" and "v1" in res.get("fallback", "v1"):
            v1 = self._get_phone_v1(token)
            if v1.get("status") in ("found", "hidden", "removed"):
                return v1
        res.pop("fallback", None)
        return res

    def _get_phone_v2(self, token: str, uuid: str,
                      auth: Dict[str, str]) -> Dict[str, Any]:
        """فلوی جدید دو مرحله‌ای (contact_info_v2 + Bearer)."""
        try:
            r = self._fetch("POST", 
                f"{self.base}/v8/postcontact/web/contact_info_v2/{token}",
                headers={**auth, "Authorization": f"Bearer {self.token}",
                         "Content-Type": "application/json"},
                json={"contact_uuid": uuid}, timeout=25)
        except requests.exceptions.RequestException as e:
            return {"status": "error", "message": str(e), "fallback": "v1"}
        if r.status_code == 401:
            raise DivarAuthError("توکن منقضی/رد شد — دوباره لاگین کنید")
        if r.status_code in (403, 429):
            self._check_block(r)
        if r.status_code == 404:
            return {"status": "error", "message": "اندپوینت v2 نیست", "fallback": "v1"}
        if r.status_code != 200:
            if looks_like_captcha(r.text):
                raise DivarBlockedError("چالش کپچا در پاسخ تماس", r.status_code, r.text)
            return {"status": "error", "message": f"HTTP {r.status_code}",
                    "fallback": "v1"}
        try:
            widgets = r.json().get("widget_list") or []
        except ValueError:
            if looks_like_captcha(r.text):
                raise DivarBlockedError("چالش کپچا در پاسخ تماس", 200, r.text)
            return {"status": "error", "message": "پاسخ غیر JSON", "fallback": "v1"}
        return self._parse_widgets_v2(widgets)

    @staticmethod
    def _parse_widgets_v2(widgets: list) -> Dict[str, Any]:
        """فقط وقتی دیوار صریحاً بگوید مخفی → hidden؛ وگرنه error تا در صف بماند."""
        return classify_contact_widgets(widgets)

    def probe_gate(self) -> Dict[str, Any]:
        """آیا این سشن هنوز برای تماس محدود است؟ سهمیهٔ شماره را نمی‌سوزاند.

        توکن جعلی `_probe`: ۴۰۴ یعنی سشن قبول شد؛ ۴۰۳/۴۲۹ یعنی هنوز پازل/محدودیت.
        """
        if not self.token:
            return {"ok": False, "state": "relogin", "http": 0,
                    "message": "توکن لاگین نیست", "divar_url": "https://divar.ir"}
        try:
            r = self._fetch(
                "GET", f"{self.base}/v8/postcontact/web/contact_info/_probe",
                headers=self._auth_headers(), timeout=20)
        except Exception as e:
            return {"ok": False, "state": "error", "http": 0,
                    "message": f"{type(e).__name__}: {str(e)[:120]}",
                    "divar_url": "https://divar.ir"}
        body = (getattr(r, "text", "") or "")[:400]
        if r.status_code == 401:
            return {"ok": False, "state": "relogin", "http": 401,
                    "message": "توکن رد شد — دوباره لاگین کنید",
                    "divar_url": "https://divar.ir"}
        if r.status_code in (403, 429) or looks_like_captcha(body):
            return {"ok": False, "state": "captcha", "http": r.status_code,
                    "message": "دیوار هنوز پازل/محدودیت می‌خواهد",
                    "divar_url": "https://divar.ir", "body": body}
        return {"ok": True, "state": "clear", "http": r.status_code,
                "message": "محدودیت این اکانت روی دیوار برداشته شده",
                "divar_url": "https://divar.ir"}

    def _get_phone_v1(self, token: str) -> Dict[str, Any]:
        """فلوی قدیمی (پشتیبان): GET contact_info با Basic."""
        r = self._fetch("GET", f"{self.base}/v8/postcontact/web/contact_info/{token}",
                          headers=self._auth_headers(), timeout=25)
        if r.status_code == 401:
            raise DivarAuthError("توکن منقضی/رد شد — دوباره لاگین کنید")
        if r.status_code in (403, 429):
            self._check_block(r)
        if r.status_code == 404:
            return {"status": "removed", "message": "آگهی حذف شده است"}
        if r.status_code != 200:
            return {"status": "error", "message": f"HTTP {r.status_code}"}
        try:
            widgets = r.json().get("widget_list") or []
        except ValueError:
            return {"status": "error", "message": "پاسخ غیر JSON"}
        return classify_contact_widgets(widgets)
