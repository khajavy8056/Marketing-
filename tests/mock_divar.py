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
    chat_sends = []       # [(token, account, text)] — پیام چت ارسال‌شده
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
            cls.chat_sends = []

    @classmethod
    def account_of(cls, auth_header: str, cookies: str = "") -> str:
        """شناسایی اکانت از هدر Basic/Bearer یا کوکی sAccessToken (فلوی v8)."""
        for prefix in ("Basic ", "Bearer "):
            if auth_header.startswith(prefix):
                return auth_header[len(prefix):].replace("tok-", "")
        for part in (cookies or "").split(";"):
            if "sAccessToken=" in part:
                return part.split("=", 1)[1].strip().replace("tok-", "")
        return ""

    @staticmethod
    def to_persian_digits(text: str) -> str:
        """شبیه‌سازی رفتار واقعی: دیوار گاهی ارقام فارسی می‌فرستد."""
        return str(text).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


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
        elif u.path == "/v8/authenticate/signinup/code":
            self._json(200, {"status": "OK", "deviceId": "dev-mock",
                             "preAuthSessionId": "pre-mock",
                             "flowType": "USER_INPUT_CODE"})
        elif u.path.startswith("/v8/postcontact/web/contact_info_v2/"):
            # فلوی جدید دو مرحله‌ای — باید Bearer/کوکی + contact_uuid درست باشد
            token = u.path.rsplit("/", 1)[-1]
            acct = MockDivar.account_of(
                self.headers.get("Authorization", ""),
                self.headers.get("Cookie", ""))
            with MockDivar.lock:
                MockDivar.contact_calls.append((token, acct))
                n = MockDivar.counters.get(acct, 0)
                cap_n = MockDivar.captcha_after.get(acct)
                if cap_n is not None and n >= cap_n and acct not in MockDivar.released:
                    return self._json(403, {"error": "captcha_required"})
                MockDivar.counters[acct] = n + 1
            if not acct:
                return self._json(401, {"error": "unauthorized"})
            if body.get("contact_uuid") != "uuid-" + token:
                return self._json(400, {"error": "bad contact_uuid"})
            if "chat" in token:
                return self._json(200, {"widget_list": [
                    {"data": {"title": "شمارهٔ مخفی‌شده است"}}]})
            if "v1only" in token:
                return self._json(404, {"error": "use v1"})  # تست fallback
            phone_ascii = "0912" + token[-7:].rjust(7, "3")
            return self._json(200, {"widget_list": [
                {"data": {"title": "شمارهٔ موبایل",
                          "value": MockDivar.to_persian_digits(phone_ascii)}}]})
        elif u.path.startswith("/v8/search/"):
            # مسیر جایگزین جامعه: همان لیست آگهی‌های شبیه‌ساز
            with MockDivar.lock:
                items = list(reversed(MockDivar.posts))
            post_list = [{"data": {"token": p["token"], "title": p["title"],
                                   "has_chat": p["has_chat"]}} for p in items]
            self._json(200, {"web_widgets": {"post_list": post_list}})
        elif u.path.startswith("/v8/chat/conversations/") and u.path.endswith("/messages"):
            # ارسال پیام چت (خودکار/دستی) — شبیه‌سازی مسیر best-effort
            token = u.path.split("/")[4]
            acct = MockDivar.account_of(
                self.headers.get("Authorization", ""),
                self.headers.get("Cookie", ""))
            if not acct:
                return self._json(401, {"error": "unauthorized"})
            text = str(body.get("message") or body.get("text") or "")
            with MockDivar.lock:
                MockDivar.chat_sends.append((token, acct, text))
            self._json(200, {"ok": True, "status": "sent"})
        elif u.path == "/v8/authenticate/signinup/code/consume":
            code = str(body.get("userInputCode") or body.get("code") or "")
            if code.strip() == "000000":
                self._json(401, {"error": "invalid code"})
            elif body.get("deviceId") and body.get("deviceId") != "dev-mock":
                self._json(401, {"error": "bad device"})
            elif body.get("preAuthSessionId") and body.get("preAuthSessionId") != "pre-mock":
                self._json(401, {"error": "bad preAuth"})
            else:
                # فلوی v8: کوکی‌های سشن ست می‌شوند (شبیه دیوار واقعی)
                self.send_response(200)
                self.send_header("Set-Cookie", "sAccessToken=tok-v8web")
                self.send_header("Set-Cookie", "sFrontToken=front-xyz")
                self.send_header("Content-Type", "application/json")
                b = json.dumps({"ok": True}, ensure_ascii=False).encode()
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
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
        elif u.path.startswith("/v8/posts-v2/web/"):
            token = u.path.rsplit("/", 1)[-1]
            if "gone" in token:
                self._json(404, {})
            else:
                # فلوی v2: uuid تماس — هم شکل قدیمی هم شکل زندهٔ تو‌در‌تو
                self._json(200, {"contact": {
                    "contact_uuid": "uuid-" + token,
                    "action_log": {"server_side_info": {"info": {
                        "post_token": token,
                        "contact_uuid": "uuid-" + token}}}}})
        elif u.path.startswith("/s/"):
            with MockDivar.lock:
                items = list(reversed(MockDivar.posts))
            bits = [f'<a href="/v/{p["token"]}/{p["token"]}">{p["title"]}</a>'
                    for p in items]
            body = ("<html><body>" + "".join(bits) + "</body></html>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif u.path.startswith("/v8/postcontact/web/contact_info_v2/"):
            pass  # در do_POST مدیریت می‌شود (متد POST است)
        elif u.path.startswith("/v8/postcontact/web/contact_info/"):
            token = u.path.rsplit("/", 1)[-1]
            acct = MockDivar.account_of(self.headers.get("Authorization", ""))
            if token == "_probe":
                cap_n = MockDivar.captcha_after.get(acct)
                if cap_n is not None and acct not in MockDivar.released:
                    return self._json(403, {"error": "captcha_required"})
                return self._json(404, {"error": "probe"})
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
