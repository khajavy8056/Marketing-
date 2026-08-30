# -*- coding: utf-8 -*-
"""نشست ورود برنامه — کوکی امضاشده + به‌خاطر سپردن روی همین رایانه.

رمز مشتری در دفترچهٔ CSV روی لینک است. اینجا فقط بعد از check_login
نشست محلی می‌سازیم. بدون اینترنت ورود نیست.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

COOKIE = "md_lic"

_PUBLIC_PREFIXES = (
    "/api/license",
)
_PUBLIC_EXACT = {
    "/", "/logo.png", "/favicon.ico",
}


def license_enforced() -> bool:
    if os.environ.get("DIVAR_SKIP_LICENSE") == "1":
        return False
    if "unittest" in sys.modules:
        return False
    return True


def is_public(path: str) -> bool:
    p = (path or "").split("?", 1)[0]
    if p in _PUBLIC_EXACT:
        return True
    return any(p == pre or p.startswith(pre + "/") for pre in _PUBLIC_PREFIXES)


def _data_dir() -> Path:
    try:
        from .paths import user_data_dir
        d = user_data_dir()
    except Exception:
        d = Path(os.environ.get("DIVAR_DATA_DIR") or "data")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _secret() -> bytes:
    p = _data_dir() / "license_secret"
    if p.exists():
        raw = p.read_bytes().strip()
        if raw:
            return raw
    raw = hashlib.sha256(os.urandom(32)).digest()
    p.write_bytes(raw)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return raw


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode((text or "") + pad)


def sign_payload(data: Dict[str, Any]) -> str:
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"),
                      sort_keys=True).encode("utf-8")
    sig = hmac.new(_secret(), blob, hashlib.sha256).digest()
    return _b64(blob) + "." + _b64(sig)


def verify_payload(token: str) -> Optional[Dict[str, Any]]:
    raw = (token or "").strip()
    if "." not in raw:
        return None
    body, _, sig = raw.partition(".")
    try:
        blob = _unb64(body)
        expect = hmac.new(_secret(), blob, hashlib.sha256).digest()
        got = _unb64(sig)
    except Exception:
        return None
    if not hmac.compare_digest(expect, got):
        return None
    try:
        data = json.loads(blob.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("u"):
        return None
    exp = data.get("exp")
    if exp is not None:
        try:
            if float(exp) < time.time() - 120:
                return None
        except (TypeError, ValueError):
            return None
    return data


def cookie_from_request(request) -> str:
    try:
        return str(request.cookies.get(COOKIE) or "")
    except Exception:
        return ""


def cookie_ok(request) -> bool:
    return verify_payload(cookie_from_request(request)) is not None


def session_public(data: Dict[str, Any]) -> Dict[str, Any]:
    left = data.get("days_left")
    try:
        left_i = int(left) if left is not None else 0
    except (TypeError, ValueError):
        left_i = 0
    span = data.get("span_days")
    try:
        span_i = int(span) if span else max(left_i, 1)
    except (TypeError, ValueError):
        span_i = max(left_i, 1)
    pct = 0
    if span_i > 0:
        pct = max(0, min(100, int(round(100.0 * left_i / span_i))))
    return {
        "ok": True,
        "username": data.get("u") or data.get("username") or "",
        "full_name": data.get("n") or data.get("full_name") or "",
        "plan": data.get("p") or data.get("plan") or "full",
        "days_left": left_i,
        "span_days": span_i,
        "pct": pct,
        "expires": data.get("e") or data.get("expires") or "",
        "started": data.get("s") or data.get("started") or "",
        "phone": data.get("ph") or "",
    }


def payload_from_check(res: Dict[str, Any]) -> Dict[str, Any]:
    row = res.get("row") or {}
    left = int(res.get("days_left") or 0)
    started = str(row.get("started") or "")
    expires = str(row.get("expires") or "")
    span = span_days(started, expires, left)
    # کوکی تا پایان امروز + روزهای مانده (حداکثر ۳۰ روز تمدید نشست محلی)
    max_age = max(3600, min(left, 30) * 86400 + 3600)
    return {
        "u": str(row.get("username") or ""),
        "n": str(res.get("full_name") or "").strip(),
        "p": str(res.get("plan") or row.get("plan") or "full"),
        "days_left": left,
        "span_days": span,
        "e": expires,
        "s": started,
        "ph": str(row.get("phone") or ""),
        "exp": time.time() + max_age,
    }


def span_days(started: str, expires: str, left: int) -> int:
    from .license_ledger import parse_day
    a, b = parse_day(started), parse_day(expires)
    if a and b and b >= a:
        n = (b - a).days
        return max(n, 1)
    return max(int(left or 0), 1)


def remember_path() -> Path:
    return _data_dir() / "license_remember.json"


def save_remember(username: str, password: str) -> None:
    rec = {"username": (username or "").strip(),
           "password": _obfuscate(password or ""),
           "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    p = remember_path()
    p.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def load_remember() -> Dict[str, str]:
    p = remember_path()
    if not p.exists():
        return {}
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(rec, dict):
        return {}
    user = str(rec.get("username") or "").strip()
    pwd = _deobfuscate(str(rec.get("password") or ""))
    if not user or not pwd:
        return {}
    return {"username": user, "password": pwd}


def clear_remember() -> None:
    p = remember_path()
    try:
        if p.exists():
            p.unlink()
    except OSError:
        pass


def _obfuscate(text: str) -> str:
    raw = (text or "").encode("utf-8")
    key = hashlib.sha256(_secret() + b"|remember").digest()
    out = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
    return _b64(out)


def _deobfuscate(text: str) -> str:
    try:
        raw = _unb64(text)
    except Exception:
        return ""
    key = hashlib.sha256(_secret() + b"|remember").digest()
    out = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
    try:
        return out.decode("utf-8")
    except Exception:
        return ""


def set_cookie(response, token: str, remember: bool, days_left: int) -> None:
    max_age = 14 * 86400 if remember else None
    if remember:
        max_age = max(86400, min(int(days_left or 1), 40) * 86400)
    response.set_cookie(
        COOKIE, token, httponly=True, samesite="lax",
        max_age=max_age, path="/")


def clear_cookie(response) -> None:
    response.delete_cookie(COOKIE, path="/")
