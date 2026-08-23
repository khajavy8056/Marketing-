# -*- coding: utf-8 -*-
"""بررسی اتصال — عیب‌یابی مرحله‌به‌مرحلهٔ مسیر ارتباط با دیوار.

این ماژول روی سیستم «خود کاربر» (با IP ایران) اجرا می‌شود و دقیقاً نشان
می‌دهد کدام لایه سالم است و کدام لایه مشکل دارد:

  ۱) DNS        — آیا api.divar.ir به IP ترجمه می‌شود؟
  ۲) اتصال TLS  — آیا اصلاً به سرور وصل می‌شویم؟ (VPN/پروکسی/فیلتر)
  ۳) جستجو      — اندپوینت جستجو چند آگهی برمی‌گرداند؟ (ساختار پاسخ سالم؟)
  ۴) جزئیات     — آگهی نمونه باز می‌شود و contact_uuid دارد؟
  ۵) شماره بدون لاگین — آزمایش علمی: آیا contact_info_v2 بدون لاگین جواب می‌دهد؟
  ۶) شماره با لاگین   — با اولین اکانت ذخیره‌شده (در صورت وجود)

به‌علاوه وضعیت پروکسی سیستم (که روی ویندوز از رجیستری خوانده می‌شود)
گزارش می‌شود — علت شماره یکِ «هیچ اتفاقی نمی‌افتد».
"""

from __future__ import annotations

import os
import socket
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from .client import UA, DivarClient

STEPS_FA_EN = {
    "dns": ("DNS — ترجمه نام دامنه", "DNS resolution"),
    "connect": ("اتصال HTTPS به سرور دیوار", "HTTPS connection to Divar"),
    "search": ("جستجوی کلمه کلیدی (اندپوینت v8)", "Keyword search (v8 endpoint)"),
    "detail": ("جزئیات آگهی نمونه + شناسه تماس", "Sample post details + contact id"),
    "phone_anon": ("دریافت شماره بدون لاگین (آزمایش)", "Phone without login (experiment)"),
    "phone_auth": ("دریافت شماره با اکانت لاگین‌شده", "Phone with logged-in account"),
    "chat": ("دسترسی چت (بهترین‌حال)", "Chat access (best-effort)"),
    "proxy": ("وضعیت پروکسی/VPN سیستم", "System proxy/VPN status"),
}


def proxy_status() -> Dict[str, Any]:
    """آیا پروکسی سیستمی (ویندوز: رجیستری / لینوکس: env) فعال است؟"""
    import urllib.request
    sys_proxies: Dict[str, str] = {}
    try:
        sys_proxies = dict(urllib.request.getproxies())
    except Exception:
        pass
    env_proxies = {k: v for k, v in os.environ.items()
                   if "proxy" in k.lower() and v}
    return {"active": bool(sys_proxies or env_proxies),
            "system": sys_proxies, "env": env_proxies}


def run_diag(base_url: Optional[str] = None, keyword: str = "آپارتمان",
             account_session: Optional[str] = None) -> Dict[str, Any]:
    """اجرای همهٔ قدم‌ها؛ خروجی: {"steps": [...], "proxy": {...}}

    هر قدم: {"key", "fa", "en", "ok", "ms", "detail"}
    """
    base = (base_url or DivarClient().base).rstrip("/")
    host = urlparse(base).hostname or "api.divar.ir"
    steps: List[Dict[str, Any]] = []
    holder: Dict[str, Any] = {}

    def add(key: str, ok: bool, detail: str, t0: float) -> None:
        fa, en = STEPS_FA_EN[key]
        steps.append({"key": key, "fa": fa, "en": en, "ok": ok,
                      "ms": int((time.time() - t0) * 1000), "detail": detail})

    def run_step(key: str, fn):
        t0 = time.time()
        try:
            add(key, True, str(fn()), t0)
        except Exception as e:
            hint = ""
            if "proxy" in str(e).lower() or type(e).__name__ == "ProxyError":
                hint = " — پروکسی سیستم مزاحم است؛ VPN را خاموش کنید"
            add(key, False, f"{type(e).__name__}: {e}{hint}", t0)

    # ۱) DNS
    def dns():
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        ips = sorted({i[4][0] for i in infos})
        return f"IP: {', '.join(ips[:3])}"
    run_step("dns", dns)

    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})

    # ۲) اتصال پایه (HEAD/GET کوچک روی جستجو — کم‌ریسک)
    def connect():
        r = s.get(f"{base}/v8/web-search/iran",
                  params={"q": keyword}, timeout=15)
        if r.status_code in (401, 403, 429):
            return f"وصل شد ولی HTTP {r.status_code} — بلاک/کپچا (VPN خاموش؟)"
        return f"وصل شد — HTTP {r.status_code}"
    run_step("connect", connect)

    # ۳) جستجو — همان زنجیرهٔ زنده (web-search → POST /v8/search → HTML)
    def search():
        from .rate import RateLimiter
        cl = DivarClient(base_url=base,
                         limiter=RateLimiter(search_delay=0, phone_delay=0,
                                             page_delay=0, jitter=0))
        posts = cl.search(keyword)
        holder["posts"] = posts
        if not posts:
            return "۰ آگهی از همهٔ مسیرهای جستجو (API+HTML)"
        return f"{len(posts)} آگهی؛ نمونه: «{(posts[0].get('title') or '?')[:40]}»"
    run_step("search", search)

    # ۴) جزئیات + uuid
    def detail():
        if not holder.get("posts"):
            raise RuntimeError("به‌خاطر شکست جستجو قابل آزمایش نیست")
        token = holder["posts"][0]["token"]
        r = s.get(f"{base}/v8/posts-v2/web/{token}", timeout=15)
        if r.status_code != 200:
            return f"HTTP {r.status_code} برای توکن {token[:12]}"
        try:
            data = r.json()
        except ValueError:
            return "پاسخ JSON نیست"
        holder["token"] = token
        from .client import extract_contact_uuid
        holder["uuid"] = extract_contact_uuid(data)
        d = data.get("data") or {}
        title = d.get("title") or holder["posts"][0].get("title") or "?"
        body = (d.get("description") or (d.get("seo") or {}).get("description")
                or d.get("subtitle") or "")
        holder["title"], holder["body"] = title, body
        where = []
        if keyword and keyword in str(title):
            where.append("عنوان")
        if keyword and keyword in str(body):
            where.append("متن")
        loc = " + ".join(where) if where else "جستجوی خود دیوار (فیلتر سمت سرور)"
        holder["match"] = loc
        snippet = str(body)[:80].replace("\n", " ")
        out = f"«{str(title)[:40]}» — کلمه در: {loc}"
        if holder["uuid"]:
            out += " — شناسه تماس آماده ✓"
        if snippet:
            out += f" | متن: {snippet}…"
        return out
    run_step("detail", detail)

    # ۵) شماره بدون لاگین — جواب سؤال «واقعاً لاگین لازم است؟»
    def phone_anon():
        if not holder.get("token"):
            raise RuntimeError("به‌خاطر قدم قبل قابل آزمایش نیست")
        r = s.post(f"{base}/v8/postcontact/web/contact_info_v2/{holder['token']}",
                   json={"contact_uuid": holder.get("uuid") or ""}, timeout=15)
        if r.status_code == 401:
            holder["anon_ok"] = False
            return "HTTP 401 — بدون لاگین نمی‌شود؛ لاگین لازم است ✓ (طراحی فعلی درست است)"
        if r.status_code == 200:
            holder["anon_ok"] = True
            return "HTTP 200 — بدون لاگین هم شماره می‌آید! (می‌توانیم لاگین را حذف کنیم)"
        return f"HTTP {r.status_code} — بدون لاگین"
    run_step("phone_anon", phone_anon)

    # ۶) شماره با اکانت ذخیره‌شده (در صورت وجود فایل سشن)
    def phone_auth():
        if holder.get("anon_ok"):
            return "لازم نیست — بدون لاگین هم کار می‌کند"
        if not account_session or not os.path.exists(account_session):
            raise RuntimeError("اکانت لاگین‌شده‌ای موجود نیست (از تب اکانت‌ها لاگین کنید)")
        cl = DivarClient(session_path=account_session, base_url=base)
        try:
            cl._load_session()
        except Exception:
            pass
        if not cl.token:
            raise RuntimeError("توکن اکانت پیدا نشد — دوباره لاگین کنید")
        res = cl.get_phone(holder["token"])
        st = res.get("status")
        if st == "found":
            return f"✓ شماره واقعی گرفته شد: {res.get('phone')}"
        if st == "hidden":
            return "✓ کار می‌کند (این آگهی فقط چت داشت)"
        return f"وضعیت: {st} — {res.get('message', '')[:80]}"
    run_step("phone_auth", phone_auth)

    # ۶.۵) دسترسی چت — بررسی بهترین‌حال (ارسال خودکار فقط از پلتفرم رسمی «کنار»)
    def chat():
        if not account_session or not os.path.exists(account_session):
            raise RuntimeError("اکانت لاگین‌شده موجود نیست — از تب اکانت‌ها لاگین کنید")
        cl = DivarClient(session_path=account_session, base_url=base)
        tried = []
        for path in ("/v8/chat/web/conversations", "/v8/chat/conversations",
                     "/v5/chat/conversations"):
            try:
                r = cl._fetch("GET", f"{base}{path}", timeout=10)
                tried.append(f"{path}→{r.status_code}")
                if r.status_code == 200:
                    return (f"دسترسی چت باز است ✓ ({path}) — ولی ارسال خودکار پیام "
                            "فقط از پلتفرم رسمی «کنار» ممکن است؛ پیام‌های ما با "
                            "قالب آماده از خود سایت/اپ ارسال می‌شوند")
                if r.status_code == 404:
                    continue
                return (f"پاسخ {r.status_code} از {path} — سشن چت "
                        f"{'معتبر نیست؛ دوباره لاگین کنید' if r.status_code in (401, 403) else 'نامشخص'}")
            except Exception as e:
                tried.append(f"{path}→{type(e).__name__}")
        raise RuntimeError(
            "اندپوینت عمومی چت وب در دسترس نبود (" + "; ".join(tried) + "). "
            "ارسال خودکار پیام در دیوار فقط از پلتفرم رسمی «کنار» (با ثبت اپ) "
            "مجاز است؛ برنامه پیام‌ها را با قالب آماده برای ارسال دستی آماده می‌کند")
    run_step("chat", chat)

    # ۷) پروکسی
    ps = proxy_status()
    if ps["active"]:
        det = "; ".join(list(ps["system"].values()) + list(ps["env"].values()))[:200]
        add("proxy", False,
            f"پروکسی فعال: {det} — اگر VPN است خاموش کنید (دیوار فقط IP ایران)", time.time())
    else:
        add("proxy", True, "پروکسی سیستمی فعال نیست ✓", time.time())

    return {"steps": steps, "proxy": ps, "base": base}
