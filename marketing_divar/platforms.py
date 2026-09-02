# -*- coding: utf-8 -*-
"""دو پلتفرم آگهی روی یک پروفایل Chromium — دیوار / شیپور.

سوییچ روشن/خاموش از تنظیمات می‌آید. لاگین هر سایت تب جدا در همان پروفایل است.
 حذف شد — پلتفرم وجود ندارد.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

IDS = ("divar", "sheypoor")

TITLES = {
    "divar": "دیوار",
    "sheypoor": "شیپور",
}

# صفحهٔ لاگین / خانه — دو سربرگ داخل یک پروفایل
LOGIN_TABS: List[Tuple[str, str]] = [
    ("divar", "https://divar.ir/user"),
    ("sheypoor", "https://www.sheypoor.com/session"),
]

CAPTCHA_TABS: List[Tuple[str, str]] = [
    ("divar", "https://divar.ir/"),
    ("sheypoor", "https://www.sheypoor.com/"),
]


def normalize_id(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if s in IDS:
        return s
    return "divar"


def lead_token(platform: str, native_id: str) -> str:
    """کلید یکتا در دیتابیس. دیوار همان توکن زنده می‌ماند تا داده قدیمی نشکند."""
    pid = normalize_id(platform)
    nid = str(native_id or "").strip()
    if not nid:
        return ""
    if pid == "divar":
        return nid
    return "%s:%s" % (pid, nid)


def split_token(token: str) -> Tuple[str, str]:
    t = str(token or "")
    for pid in ("sheypoor",):
        pre = pid + ":"
        if t.startswith(pre):
            return pid, t[len(pre):]
    return "divar", t


def listing_url(platform: str, native_id: str, slug: str = "") -> str:
    pid = normalize_id(platform)
    nid = str(native_id or "").strip()
    if pid == "sheypoor":
        if slug:
            return "https://www.sheypoor.com/v/%s-%s.html" % (slug, nid)
        return "https://www.sheypoor.com/v/%s.html" % nid
    if slug:
        return "https://divar.ir/v/%s/%s" % (slug, nid)
    return "https://divar.ir/v/%s" % nid


def enabled_from_settings(s: Dict[str, Any] | None) -> List[str]:
    s = s or {}
    out = []
    for pid in IDS:
        key = "platform_%s" % pid
        if s.get(key, True) is False or s.get(key) in (0, "0", "false", "False"):
            continue
        out.append(pid)
    if not out:
        out = ["divar"]
    return out


def login_urls(enabled: List[str] | None = None) -> List[str]:
    want = set(enabled or IDS)
    return [url for pid, url in LOGIN_TABS if pid in want]


def captcha_urls(enabled: List[str] | None = None, primary: str = "") -> List[str]:
    want = set(enabled or IDS)
    urls = [url for pid, url in CAPTCHA_TABS if pid in want]
    if primary:
        urls = [primary] + [u for u in urls if u != primary]
    return urls
