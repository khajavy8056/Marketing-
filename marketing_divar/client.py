# -*- coding: utf-8 -*-
"""کلاینت ارتباط با دیوار (غیررسمی) — جستجو، لاگین با کد تایید، دریافت شماره تماس.

اندپوینت‌ها بر اساس سورس باز پکیج `divar` نسخه ۲.۰.۱ (PyPI) و ابزارهای
متن‌باز مشابه استخراج و بازنویسی شده‌اند؛ ممکن است دیوار بدون اطلاع تغییرشان دهد.

نکته مهم: اجرای این ماژول باید از IP ایران انجام شود.
"""

from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

BASE = "https://api.divar.ir"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

HIDDEN_MARKER = "شماره مخفی شده است"


class DivarAuthError(Exception):
    """توکن وجود ندارد، منقضی شده یا رد شده است."""


class DivarClient:
    """کلاینت سشن‌دار دیوار با ذخیره‌سازی توکن لاگین."""

    def __init__(self, session_path: str = "data/session.json"):
        self.session_path = Path(session_path)
        self.http = requests.Session()
        self.http.headers.update({"User-Agent": UA, "Accept": "application/json"})
        self.token: Optional[str] = None
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
        try:  # فقط مالک ماشین بتواند بخواند (حاوی توکن دسترسی است)
            os.chmod(self.session_path, 0o600)
        except OSError:
            pass

    def is_logged_in(self) -> bool:
        return bool(self.token)

    # --------------------------------------------------------------- login --
    def request_otp(self, phone: str) -> bool:
        """گام ۱: ارسال کد تایید پیامکی به شماره (فرمت 09xxxxxxxxx)."""
        r = self.http.post(f"{BASE}/v5/auth/authenticate",
                           json={"phone": str(phone)}, timeout=25)
        if r.status_code in (200, 201):
            return True
        raise RuntimeError(f"ارسال کد ناموفق: HTTP {r.status_code} — {r.text[:200]}")

    def confirm_otp(self, phone: str, code: str) -> str:
        """گام ۲: تأیید کد و دریافت توکن JWT."""
        r = self.http.post(f"{BASE}/v5/auth/confirm",
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
        """جریان کامل لاگین: شماره بگیر → کد بفرست → کد تأیید را بپرس → ذخیره کن."""
        if phone is None:
            phone = input("شماره موبایل (09xxxxxxxxx): ").strip()
        if not phone.startswith("09") or len(phone) != 11:
            raise ValueError("فرمت شماره درست نیست؛ باید 11 رقم و با 09 شروع شود")
        print("در حال ارسال کد تایید پیامکی…")
        self.request_otp(phone)
        code = input("کد ۶ رقمی دریافتی از پیامک دیوار: ").strip()
        self.confirm_otp(phone, code)
        print("✓ لاگین موفق؛ توکن در فایل سشن ذخیره شد (لاگین مجدد تا انقضای توکن لازم نیست)")

    def _auth_headers(self) -> Dict[str, str]:
        if not self.token:
            raise DivarAuthError("ابتدا لاگین کنید (فرمان: login)")
        return {"Authorization": f"Basic {self.token}"}

    # -------------------------------------------------------------- search --
    def search(self, query: str, cities: Optional[List[int]] = None,
               page: int = 1) -> List[Dict[str, Any]]:
        """جستجوی کلمه‌کلیدی در آگهی‌ها.

        cities: کد شهرها مثل [1] تهران، [2] کرج، [3] مشهد، [4] اصفهان —
        None یعنی کل ایران.
        خروجی: لیستی از دیکشنری (token/title/subtitle/…) برای هر آگهی.
        """
        params: Dict[str, Any] = {"q": query}
        if cities:
            params["cities"] = ",".join(str(c) for c in cities)
        if page and page > 1:
            params["page"] = page
        r = self.http.get(f"{BASE}/v8/web-search/iran", params=params, timeout=25)
        r.raise_for_status()
        data = r.json()
        return self._extract_post_list(data)

    @staticmethod
    def _extract_post_list(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """استخراج مقاوم آگهی‌ها از ساختار پاسخ جستجو (web_widgets.post_list)."""
        raw: List[Dict[str, Any]] = []
        web_widgets = data.get("web_widgets") or {}
        if isinstance(web_widgets, dict):
            pl = web_widgets.get("post_list")
            if isinstance(pl, list):
                raw = pl
        posts: List[Dict[str, Any]] = []
        for item in raw:
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

    # ---------------------------------------------------------- post detail --
    def get_post(self, token: str) -> Dict[str, Any]:
        """جزئیات کامل آگهی (عنوان، توضیحات، فیلدها)."""
        r = self.http.get(f"{BASE}/v8/posts-v2/web/{token}", timeout=25)
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------ phone 🔑 --
    def get_phone(self, token: str) -> Dict[str, Any]:
        """دریافت شماره تماس آگهی (نیاز به لاگین).

        خروجی: {"status": "found", "phone": "09..."}
               {"status": "hidden"}   → آگهی‌دهنده نمایش شماره را غیرفعال کرده
               {"status": "error", "message": "..."}
        """
        r = self.http.get(f"{BASE}/v8/postcontact/web/contact_info/{token}",
                          headers=self._auth_headers(), timeout=25)
        if r.status_code in (401, 403):
            raise DivarAuthError(
                f"توکن رد شد (HTTP {r.status_code}) — دوباره لاگین کنید")
        if r.status_code == 404:
            return {"status": "error", "message": "آگهی حذف شده است"}
        if r.status_code == 429:
            return {"status": "error",
                    "message": "محدودیت نرخ دیوار (429) — سرعت را کم کنید"}
        if r.status_code != 200:
            return {"status": "error",
                    "message": f"HTTP {r.status_code}: {r.text[:150]}"}
        try:
            widgets = r.json().get("widget_list") or []
            for w in widgets:
                d = (w or {}).get("data") or {}
                if d.get("title") == HIDDEN_MARKER:
                    return {"status": "hidden"}
                action = d.get("action") or {}
                payload = action.get("payload") or {}
                phone = payload.get("phone_number")
                if phone:
                    phone = str(phone)
                    if not phone.startswith("0"):
                        phone = "0" + phone  # نرمال‌سازی 98xxx → 098xxx
                    return {"status": "found", "phone": phone}
            return {"status": "hidden"}  # ویجت شماره‌ای نداشت
        except (ValueError, KeyError, TypeError) as e:
            return {"status": "error", "message": f"پاسخ غیرمنتظره: {e}"}

    # ------------------------------------------------------------- utility --
    @staticmethod
    def polite_sleep(base: float = 3.0, jitter: float = 1.5) -> None:
        """تاخیر تصادفی بین درخواست‌ها برای کم‌تر دیده‌شدن و بلاک نشدن."""
        time.sleep(base + random.uniform(0, jitter))
