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

    def __init__(self, code: int, body: bytes):
        self.status_code = code
        self._body = body
        self.text = body.decode("utf-8", errors="replace")

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
        return fn(url, **kw)


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
                return _UrllibResp(resp.status, resp.read())
        except urllib.error.HTTPError as e:
            return _UrllibResp(e.code, e.read() or b"")


def default_base() -> str:
    """آدرس پایه API — با متغیر DIVAR_BASE_URL قابل تغییر (برای تست با شبیه‌ساز)."""
    import os
    return os.environ.get("DIVAR_BASE_URL", "https://api.divar.ir")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

CITY_SLUGS = {
    1: "tehran", 2: "karaj", 3: "mashhad", 4: "isfahan",
    5: "shiraz", 6: "ahvaz", 7: "tabriz", 8: "qom",
    "1": "tehran", "2": "karaj", "3": "mashhad", "4": "isfahan",
    "5": "shiraz", "6": "ahvaz", "7": "tabriz", "8": "qom",
}


def city_slug(cities: Optional[List[Any]]) -> str:
    """اسلاگ شهر برای HTML سایت؛ بدون شهر = iran."""
    if not cities:
        return "iran"
    c = cities[0]
    mapped = CITY_SLUGS.get(c) or CITY_SLUGS.get(str(c))
    if mapped:
        return mapped
    s = str(c).strip().lower()
    return s if s and not s.isdigit() else "iran"


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
# نشانه‌های احتمالی چالش کپچا در بدنه پاسخ
CAPTCHA_MARKERS = ("captcha", "challenge", "arkose", "rcsc", "puzzle")


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
    t = (text or "").lower()
    return any(m in t for m in CAPTCHA_MARKERS)


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
    def _load_session(self) -> None:
        if self.session_path.exists():
            try:
                data = json.loads(self.session_path.read_text(encoding="utf-8"))
                self.token = data.get("token")
                # بازیابی کوکی‌های سشن (برای فلوی v8 که کوکی‌محور است)
                for k, v in (data.get("cookies") or {}).items():
                    self.http.cookies.set(k, v)
            except Exception:
                self.token = None

    def _save_session(self, phone: str) -> None:
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            cookies = {c.name: c.value for c in self.http.cookies}
        except Exception:
            cookies = {}
        self.session_path.write_text(
            json.dumps({"phone": phone, "token": self.token, "cookies": cookies,
                        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")},
                       ensure_ascii=False, indent=2),
            encoding="utf-8")
        try:  # فایل حاوی توکن دسترسی است
            os.chmod(self.session_path, 0o600)
        except OSError:
            pass

    def is_logged_in(self) -> bool:
        return bool(self.token)

    def reload_session(self) -> None:
        """خواندن مجدد توکن از دیسک (مثلاً بعد از لاگین مجدد از ترمینال دیگر)."""
        self._load_session()

    # --------------------------------------------------------------- login --
    def request_otp(self, phone: str) -> bool:
        """گام ۱: درخواست کد تایید پیامکی — v5 اصلی، v8 پشتیبان."""
        r = self._fetch("POST", f"{self.base}/v5/auth/authenticate",
                           json={"phone": str(phone)}, timeout=25)
        if r.status_code in (200, 201):
            return True
        if r.status_code in (403, 429) or looks_like_captcha(r.text):
            raise DivarBlockedError("درخواست کد محدود شد (شاید تلاش‌های زیاد OTP)",
                                    r.status_code, r.text)
        # مسیر جدید v8 (کوکی‌محور) — اگر v5 غیرفعال شده باشد
        try:
            r2 = self._fetch("POST", 
                f"{self.base}/v8/authenticate/signinup/code",
                json={"phoneNumber": str(phone)},
                headers={"st-auth-mode": "cookie"}, timeout=25)
            if r2.status_code in (200, 201):
                return True
        except requests.exceptions.RequestException:
            pass
        raise RuntimeError(
            f"ارسال کد ناموفق: v5→HTTP {r.status_code}؛ "
            f"v8→HTTP {getattr(r2, 'status_code', '—')} — {r.text[:150]}")

    def confirm_otp(self, phone: str, code: str) -> str:
        """گام ۲: تأیید کد و دریافت توکن — v5 اصلی، v8 پشتیبان."""
        r = self._fetch("POST", f"{self.base}/v5/auth/confirm",
                           json={"phone": str(phone), "code": str(code)},
                           timeout=25)
        if r.status_code in (200, 201):
            tok = (r.json() or {}).get("token")
            if tok:
                self.token = tok
                self._save_session(phone)
                return tok
        # مسیر جدید v8 — سشن کوکی‌محور (sAccessToken/sFrontToken)
        try:
            r2 = self._fetch("POST", 
                f"{self.base}/v8/authenticate/signinup/code/consume",
                json={"code": str(code), "phoneNumber": str(phone)},
                headers={"st-auth-mode": "cookie"}, timeout=25)
            if r2.status_code in (200, 201):
                tok = ""
                try:
                    tok = (r2.json() or {}).get("token") or ""
                except ValueError:
                    pass
                # در فلوی v8 اعتبارسنجی با کوکی‌های ست‌شده توسط سرور انجام می‌شود
                if tok or self.http.cookies.get("sAccessToken"):
                    self.token = tok or self.http.cookies.get("sAccessToken")
                    self._save_session(phone)
                    return self.token
                raise DivarAuthError("پاسخ v8 نه توکن داشت نه کوکی سشن")
        except requests.exceptions.RequestException as e:
            raise DivarAuthError(f"خطای شبکه در تأیید v8: {e}")
        raise DivarAuthError(
            f"کد تأیید نامعتبر یا منقضی (v5→HTTP {r.status_code}؛ "
            f"v8→HTTP {getattr(r2, 'status_code', '—')})")

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
               page: int = 1) -> List[Dict[str, Any]]:
        """جستجوی کلمه‌کلیدی در آگهی‌ها (بدون لاگین، ارزان)."""
        self.limiter.wait("search")
        params: Dict[str, Any] = {"q": query}
        if cities:
            params["cities"] = ",".join(str(c) for c in cities)
        if page and page > 1:
            params["page"] = page
        try:
            r = self._fetch("GET", f"{self.base}/v8/web-search/iran",
                            params=params, timeout=25)
            self._check_block(r)
            if r.status_code in (401, 403, 451):
                raise DivarBlockedError(
                    f"دیوار جستجو را رد کرد (HTTP {r.status_code}) — اگر VPN/پروکسی "
                    "روشن است خاموش کنید؛ دیوار فقط با IP ایران جواب می‌دهد",
                    status=r.status_code)
            r.raise_for_status()
            posts = self._extract_post_list(r.json())
            if posts:
                return posts
            _log("warning", "API جستجو ۰ آگهی داد — امتحان HTML خود سایت دیوار")
        except DivarBlockedError:
            raise  # بلاک واقعی: فشار نیاوریم
        except Exception as e:
            _log("warning", f"API جستجو ناموفق ({type(e).__name__}: {str(e)[:100]}) "
                            "— امتحان HTML خود سایت دیوار")
        # ── راه دوم: خواندن HTML صفحهٔ جستجوی خود سایت دیوار ──
        return self._search_html(query, cities, page)

    _HTML_PAIR = re.compile(r'href="/v/([^"/]+)/([A-Za-z0-9_-]{4,})"')

    @staticmethod
    def _parse_search_html(html: str) -> List[Dict[str, Any]]:
        """استخراج توکن + عنوان (از slug) در HTML صفحهٔ جستجوی سایت دیوار."""
        import urllib.parse as _up
        posts, seen = [], set()
        for slug, token in DivarClient._HTML_PAIR.findall(html):
            if token in seen or token in ("chat", "rules", "about"):
                continue
            seen.add(token)
            title = _up.unquote(slug).replace("-", " ").strip()
            posts.append({"token": token, "title": title or "—",
                          "subtitle": "", "url": f"https://divar.ir/v/{slug}/{token}"})
        return posts[:24]

    def _search_html(self, query: str, cities=None, page: int = 1):
        """جستجو از HTML سایت (راه نجات وقتی API خاموش/تغییرشکل‌داده است)."""
        host = "https://divar.ir"
        if self.base.startswith("http") and "divar.ir" not in self.base:
            host = self.base  # شبیه‌ساز تست
        city = city_slug(cities)
        url = f"{host}/s/{city}"
        params = {"q": query}
        if page and page > 1:
            params["page"] = page
        r = self._fetch("GET", url, params=params, timeout=25)
        if r.status_code != 200:
            raise DivarBlockedError(
                f"HTML جستجو هم HTTP {r.status_code} داد", r.status_code, r.text[:200])
        posts = self._parse_search_html(r.text)
        _log("success" if posts else "warning",
             f"جستجوی HTML سایت: {len(posts)} آگهی پیدا شد" if posts
             else "جستجوی HTML سایت هم ۰ آگهی داد")
        return posts

    @staticmethod
    def _extract_post_list(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        web_widgets = data.get("web_widgets") or {}
        raw = web_widgets.get("post_list") if isinstance(web_widgets, dict) else None
        posts: List[Dict[str, Any]] = []
        for item in raw or []:
            d = (item or {}).get("data") or {}
            tok = d.get("token")
            if not tok:
                continue
            posts.append({
                "token": tok,
                "title": d.get("title") or "",
                "subtitle": d.get("middle_description_text") or "",
                "top": d.get("top_description_text") or "",
                "bottom": d.get("bottom_description_text") or "",
                "has_chat": bool(d.get("has_chat", False)),
                "url": f"https://divar.ir/v/{tok}",
            })
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
            return (r.json().get("contact") or {}).get("contact_uuid")
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
        """پارس پاسخ v2: عنوان «شمارهٔ موبایل» → value (ممکن است فارسی باشد)."""
        for w in widgets:
            d = (w or {}).get("data") or {}
            title = d.get("title") or ""
            if MOBILE_MARKER in title and d.get("value"):
                phone = normalize_phone(d.get("value"))
                if phone:
                    return {"status": "found", "phone": phone}
            if HIDDEN_MARKER_V2 in title:
                return {"status": "hidden"}
        # شماره‌ای در ویجت‌ها نبود → فقط چت
        return {"status": "hidden"}

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
        for w in widgets:
            d = (w or {}).get("data") or {}
            if d.get("title") == HIDDEN_MARKER:
                return {"status": "hidden"}
            payload = ((d.get("action") or {}).get("payload") or {})
            phone = normalize_phone(payload.get("phone_number"))
            if phone:
                return {"status": "found", "phone": phone}
        return {"status": "hidden"}
