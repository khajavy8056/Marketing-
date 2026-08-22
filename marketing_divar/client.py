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
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from .rate import RateLimiter

def default_base() -> str:
    """آدرس پایه API — با متغیر DIVAR_BASE_URL قابل تغییر (برای تست با شبیه‌ساز)."""
    import os
    return os.environ.get("DIVAR_BASE_URL", "https://api.divar.ir")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

HIDDEN_MARKER = "شماره مخفی شده است"
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

    # ------------------------------------------------------------- session --
    def _load_session(self) -> None:
        if self.session_path.exists():
            try:
                data = json.loads(self.session_path.read_text(encoding="utf-8"))
                self.token = data.get("token")
            except Exception:
                self.token = None

    def _save_session(self, phone: str) -> None:
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_path.write_text(
            json.dumps({"phone": phone, "token": self.token,
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
        """گام ۱: درخواست کد تایید پیامکی (فرمت 09xxxxxxxxx)."""
        r = self.http.post(f"{self.base}/v5/auth/authenticate",
                           json={"phone": str(phone)}, timeout=25)
        if r.status_code in (200, 201):
            return True
        if r.status_code in (403, 429) or looks_like_captcha(r.text):
            raise DivarBlockedError("درخواست کد محدود شد (شاید تلاش‌های زیاد OTP)",
                                    r.status_code, r.text)
        raise RuntimeError(f"ارسال کد ناموفق: HTTP {r.status_code} — {r.text[:200]}")

    def confirm_otp(self, phone: str, code: str) -> str:
        """گام ۲: تأیید کد و دریافت توکن JWT."""
        r = self.http.post(f"{self.base}/v5/auth/confirm",
                           json={"phone": str(phone), "code": str(code)},
                           timeout=25)
        if r.status_code in (200, 201):
            tok = r.json().get("token")
            if not tok:
                raise RuntimeError("پاسخ موفق ولی توکن نداشت: " + r.text[:200])
            self.token = tok
            self._save_session(phone)
            return tok
        raise DivarAuthError(f"کد تأیید نامعتبر یا منقضی (HTTP {r.status_code})")

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
            raise DivarBlockedError("دسترسی ممنوع (403) — ممکن است بلاک IP باشد",
                                    403, r.text)

    def search(self, query: str, cities: Optional[List[int]] = None,
               page: int = 1) -> List[Dict[str, Any]]:
        """جستجوی کلمه‌کلیدی در آگهی‌ها (بدون لاگین، ارزان)."""
        self.limiter.wait("search")
        params: Dict[str, Any] = {"q": query}
        if cities:
            params["cities"] = ",".join(str(c) for c in cities)
        if page and page > 1:
            params["page"] = page
        r = self.http.get(f"{self.base}/v8/web-search/iran", params=params, timeout=25)
        self._check_block(r)
        r.raise_for_status()
        return self._extract_post_list(r.json())

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
        r = self.http.get(f"{self.base}/v8/posts-v2/web/{token}", timeout=25)
        self._check_block(r)
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------ phone 🔑 --
    def get_phone(self, token: str) -> Dict[str, Any]:
        """دریافت شماره تماس آگهی (نیاز به لاگین؛ گران‌ترین درخواست از نظر ریسک).

        خروجی: {"status": "found"|"hidden"|"removed"|"error", ...}
        خطاها: DivarAuthError (لاگین) / DivarBlockedError (کپچا/بلاک/429)
        """
        self.limiter.wait("phone")
        r = self.http.get(f"{self.base}/v8/postcontact/web/contact_info/{token}",
                          headers=self._auth_headers(), timeout=25)
        if r.status_code == 401:
            raise DivarAuthError("توکن منقضی/رد شد — دوباره لاگین کنید")
        if r.status_code in (403, 429):
            self._check_block(r)  # DivarBlockedError
        if r.status_code == 404:
            return {"status": "removed", "message": "آگهی حذف شده است"}
        if r.status_code != 200:
            # گاهی چالش کپچا با 200/جای دیگر می‌آید؛ بدنه را هم چک می‌کنیم
            if looks_like_captcha(r.text):
                raise DivarBlockedError("چالش کپچا در پاسخ تماس",
                                        r.status_code, r.text)
            return {"status": "error", "message": f"HTTP {r.status_code}: {r.text[:150]}"}
        try:
            widgets = r.json().get("widget_list") or []
        except ValueError:
            if looks_like_captcha(r.text):
                raise DivarBlockedError("چالش کپچا در پاسخ تماس", 200, r.text)
            return {"status": "error", "message": "پاسخ غیر JSON"}
        for w in widgets:
            d = (w or {}).get("data") or {}
            if d.get("title") == HIDDEN_MARKER:
                return {"status": "hidden"}
            payload = ((d.get("action") or {}).get("payload") or {})
            phone = payload.get("phone_number")
            if phone:
                phone = str(phone)
                if not phone.startswith("0"):
                    phone = "0" + phone  # نرمال‌سازی 98… → 098…
                return {"status": "found", "phone": phone}
        return {"status": "hidden"}
