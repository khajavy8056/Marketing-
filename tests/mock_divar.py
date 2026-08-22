# -*- coding: utf-8 -*-
"""سرور شبیه‌ساز API دیوار — برای تست یکپارچه بدون نیاز به اینترنت/IP ایران.

شبیه‌سازی می‌کند:
- جستجو: GET /v8/web-search/iran?q=...&page=... (پست‌ها می‌توانند حین اجرا اضافه شوند)
- لاگین: POST /v5/auth/authenticate و /v5/auth/confirm → token
- شماره: GET /v8/postcontact/web/contact_info/{token} با Authorization
  * توکن آگهی شامل 'chat' → شماره مخفی (فقط چت)
  * اکانتِ 'captcha-acct' بعد از N درخواست → 403 کپچا، تا وقتی release شود
  * 429 اگر پشت‌سرهم سریع بزنند (سریع‌تر از min_interval)
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class MockDivar:
    """وضعیت شبیه‌ساز + مدیریت آن (استاتیک برای دسترسی Handler)."""

    lock = threading.Lock()
    posts = []            # [{"token","title","has_chat"}]
    captcha_after = {}    # account -> N (بعد از N درخواست موفق، کپچا)
    released = set()      # اکانت‌هایی که اپراتور آزاد کرده
    counters = {}         # account -> تعداد درخواست موفق
    contact_calls = []    # [(token, account)]
    min_interval = 0.0    # برای تست 429 (اختیاری)

    @classmethod
    def add_posts(cls, posts):
        with cls.lock:
            cls.posts.extend(posts)

    @classmethod
    def reset(cls):
        with cls.lock:
            cls.posts = []
            cls.captcha_after = {}
            cls.released = set()
            cls.counters = {}
            cls.contact_calls = []

    @classmethod
    def account_of(cls, auth_header: str) -> str:
        # Authorization: Basic tok-<name>
        if not auth_header or not auth_header.startswith("Basic "):
            return ""
        return auth_header[6:].replace("tok-", "")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # خاموش‌کردن لاگ پرسر‌و‌صدا
        pass

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = {}
        if u.path == "/v5/auth/authenticate":
            self._json(200, {})
        elif u.path == "/v5/auth/confirm":
            # کد «000000» به‌عنوان کد اشتباه شبیه‌سازی می‌شود (برای تست خطا)
            if body.get("code") == "000000":
                self._json(401, {"error": "invalid code"})
            else:
                self._json(200, {"token": "tok-ok"})
        else:
            self._json(404, {})

    def do_GET(self):
        u = urlparse(self.path)
        qs = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/v8/web-search/iran":
            page = int(qs.get("page", 1))
            with MockDivar.lock:
                # مثل دیوار: جدیدترین آگهی همیشه اول صفحه ۱ است
                items = list(reversed(MockDivar.posts))
            per = 5
            chunk = items[(page - 1) * per: page * per]
            post_list = []
            for p in chunk:
                post_list.append({"data": {
                    "token": p["token"], "title": p["title"],
                    "middle_description_text": "قیمت نمونه",
                    "top_description_text": "تهران",
                    "bottom_description_text": "۱ دقیقه پیش",
                    "has_chat": p["has_chat"]}})
            self._json(200, {"web_widgets": {"post_list": post_list}})
        elif u.path.startswith("/v8/postcontact/web/contact_info/"):
            token = u.path.rsplit("/", 1)[-1]
            acct = MockDivar.account_of(self.headers.get("Authorization", ""))
            with MockDivar.lock:
                MockDivar.contact_calls.append((token, acct))
                n = MockDivar.counters.get(acct, 0)
                # کپچا برای اکانت مشخص بعد از N موفقیت (و تا release)
                cap_n = MockDivar.captcha_after.get(acct)
                if cap_n is not None and n >= cap_n and acct not in MockDivar.released:
                    return self._json(403, {"error": "captcha_required"})
                MockDivar.counters[acct] = n + 1
            if "chat" in token:
                return self._json(200, {"widget_list": [
                    {"data": {"title": "شماره مخفی شده است"}}]})
            phone = "0912" + token[-7:].rjust(7, "3")
            widget = {"data": {"title": "شماره تماس",
                               "action": {"payload": {"phone_number": phone}}}}
            return self._json(200, {"widget_list": [widget]})
        else:
            self._json(404, {})


def start_mock() -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv
