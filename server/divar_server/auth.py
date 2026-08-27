# -*- coding: utf-8 -*-
"""احراز هویت پنل سرور — صفحهٔ لاگین قبل از بارگذاری پنل.

- پیش‌فرض: کاربر `admin` با رمز `admin` (مجبور به تغییر رمز در اولین ورود).
- رمز با PBKDF2-HMAC-SHA256 هش می‌شود (بدون وابستگی خارجی).
- نشست‌ها با توکن تصادفی + کوکی `divar_session` (HttpOnly / SameSite) مدیریت می‌شوند.

فایل اعتبارنامه: {DATA_DIR}/server-auth.json
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "admin"
SESSION_TTL_SEC = 12 * 3600          # ۱۲ ساعت
COOKIE_NAME = "divar_session"
_ITERATIONS = 240_000


def _data_dir() -> Path:
    return Path(os.environ.get("DIVAR_DATA_DIR", Path.home() / ".local" / "share" / "khajavy-lead"))


def creds_path() -> Path:
    return _data_dir() / "server-auth.json"


def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return "pbkdf2$%d$%s$%s" % (_ITERATIONS, salt.hex(), dk.hex())


def _verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(salt_hex), int(iters))
        return secrets.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


class AuthManager:
    """نگه‌دارندهٔ وضعیت احراز هویت + نشست‌ها (thread-safe)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._creds_path = creds_path()
        self._ensure_credentials()

    # ------------------------------------------------------ ذخیره اعتبار --
    def _ensure_credentials(self) -> None:
        if not self._creds_path.exists():
            self._write({"users": {
                DEFAULT_USER: {
                    "password_hash": _hash_password(DEFAULT_PASSWORD),
                    "must_change_password": True,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            }})

    def _read(self) -> Dict[str, Any]:
        try:
            data = json.loads(self._creds_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write(self, data: Dict[str, Any]) -> None:
        self._creds_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._creds_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, self._creds_path)

    # ------------------------------------------------------------ ورود --
    def authenticate(self, username: str, password: str) -> Dict[str, Any]:
        username = (username or "").strip()
        data = self._read()
        rec = (data.get("users") or {}).get(username)
        if not rec or not _verify_password(password or "", rec.get("password_hash", "")):
            return {"ok": False, "message": "نام کاربری یا رمز اشتباه است"}
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = {
                "user": username,
                "created_at": time.time(),
                "last_seen": time.time(),
            }
        return {
            "ok": True,
            "token": token,
            "username": username,
            "must_change_password": bool(rec.get("must_change_password")),
        }

    def change_password(self, token: str, current: str, new: str) -> Dict[str, Any]:
        sess = self.get_session(token)
        if not sess:
            return {"ok": False, "message": "نشست معتبر نیست — دوباره وارد شوید"}
        username = sess["user"]
        if not new or len(new) < 6:
            return {"ok": False, "message": "رمز جدید باید حداقل ۶ کاراکتر باشد"}
        data = self._read()
        rec = (data.get("users") or {}).get(username)
        if not rec:
            return {"ok": False, "message": "کاربر پیدا نشد"}
        # در اولین ورود رمز فعلی = رمز پیش‌فرض؛ ولی همیشه بررسی می‌کنیم
        if not _verify_password(current or "", rec.get("password_hash", "")):
            return {"ok": False, "message": "رمز فعلی اشتباه است"}
        data["users"][username]["password_hash"] = _hash_password(new)
        data["users"][username]["must_change_password"] = False
        data["users"][username]["changed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._write(data)
        return {"ok": True, "message": "رمز با موفقیت تغییر کرد"}

    # ------------------------------------------------------------ نشست --
    def get_session(self, token: Optional[str]) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        with self._lock:
            sess = self._sessions.get(token)
            if not sess:
                return None
            if time.time() - sess["created_at"] > SESSION_TTL_SEC:
                self._sessions.pop(token, None)
                return None
            sess["last_seen"] = time.time()
            return dict(sess)

    def logout(self, token: Optional[str]) -> None:
        if token:
            with self._lock:
                self._sessions.pop(token, None)

    def must_change_password(self, token: Optional[str]) -> bool:
        sess = self.get_session(token)
        if not sess:
            return False
        data = self._read()
        rec = (data.get("users") or {}).get(sess["user"], {})
        return bool(rec.get("must_change_password"))


# نمونهٔ سراسری (در app.py ساخته می‌شود)
auth: AuthManager = AuthManager()
