# -*- coding: utf-8 -*-
"""دفترچهٔ لایسنس — یک فایل سطری + ساعت واقعی از اینترنت.

بخش ۱: هنوز صفحهٔ ورود نیست. فقط خواندن دفترچه و تاریخ سرور.
لینک را با DIVAR_LICENSE_URL عوض کنید (مثلاً Gist خصوصی).
"""

from __future__ import annotations

import csv
import io
import os
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

# لینک خام همین فایل روی شاخهٔ جلسه — بعداً می‌تواند Gist خصوصی باشد
DEFAULT_URL = (
    "https://raw.githubusercontent.com/khajavy8056/Marketing-/"
    "arena/01a04911-marketing/license/ok.csv"
)

FIELDS = (
    "first_name", "last_name", "username", "password", "phone",
    "plan", "started", "expires", "status", "note",
)

_REASON_FA = {
    "ok": "ورود مجاز است",
    "bad_user": "این نام کاربری در دفترچه نیست",
    "bad_pass": "رمز عبور درست نیست",
    "disabled": "این حساب توسط فروشنده قطع شده است",
    "expired": "اعتبار این حساب تمام شده است",
    "no_internet": "بدون اینترنت نمی‌توان اعتبار را بررسی کرد",
    "bad_file": "دفترچهٔ اعتبار خوانده نشد — لینک یا فایل را بررسی کنید",
    "bad_row": "اطلاعات این سطر ناقص است",
}


def ledger_url(explicit: str = "") -> str:
    return (explicit or os.environ.get("DIVAR_LICENSE_URL") or DEFAULT_URL).strip()


def parse_http_date(value: str) -> Optional[datetime]:
    """ساعت واقعی شبکه از هدر Date — نه ساعت ویندوز مشتری."""
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_day(value: str) -> Optional[date]:
    t = (value or "").strip()[:10]
    if not t:
        return None
    try:
        return date.fromisoformat(t)
    except ValueError:
        return None


def _normalize_row(raw: Dict[str, str]) -> Dict[str, str]:
    out = {k: (raw.get(k) or "").strip() for k in FIELDS}
    out["username"] = out["username"].casefold()
    out["plan"] = (out["plan"] or "full").strip().lower()
    if out["plan"] not in ("demo", "full"):
        out["plan"] = "full"
    out["status"] = (out["status"] or "active").strip().lower()
    return out


def parse_csv(text: str) -> List[Dict[str, str]]:
    blob = (text or "").lstrip("\ufeff")
    if not blob.strip():
        return []
    reader = csv.DictReader(io.StringIO(blob))
    rows: List[Dict[str, str]] = []
    for rec in reader:
        if not isinstance(rec, dict):
            continue
        row = _normalize_row({str(k).strip(): str(v or "") for k, v in rec.items()
                              if k is not None})
        if row["username"]:
            rows.append(row)
    return rows


def fetch_ledger(url: str = "", timeout: float = 20.0
                 ) -> Tuple[List[Dict[str, str]], Optional[datetime], str]:
    """یک درخواست: متن دفترچه + ساعت اینترنت از هدر Date.

    خروجی: (سطرها, now_utc, error)
    error خالی = موفق.
    """
    target = ledger_url(url)
    if not target or urlparse(target).scheme not in ("http", "https"):
        return [], None, "bad_file"
    try:
        import requests
        r = requests.get(target, timeout=timeout, headers={
            "User-Agent": "DivarMarketing-License/1",
            "Accept": "text/csv,text/plain,*/*",
            "Cache-Control": "no-cache",
        })
    except Exception:
        return [], None, "no_internet"
    now = parse_http_date(r.headers.get("Date") or "")
    if r.status_code != 200:
        return [], now, "bad_file"
    body = r.content.decode("utf-8-sig", errors="replace")
    try:
        rows = parse_csv(body)
    except Exception:
        return [], now, "bad_file"
    if now is None:
        return rows, None, "no_internet"
    return rows, now, ""


def days_left(expires: str, now: datetime) -> Optional[int]:
    day = parse_day(expires)
    if not day:
        return None
    return (day - now.date()).days


def check_login(username: str, password: str, url: str = "",
                timeout: float = 20.0) -> Dict[str, Any]:
    """تطبیق یوزر/رمز با دفترچه و تاریخ واقعی اینترنت."""
    user = (username or "").strip().casefold()
    pwd = (password or "").strip()
    rows, now, err = fetch_ledger(url, timeout=timeout)
    if err:
        return {"ok": False, "reason": err, "message_fa": _REASON_FA[err],
                "days_left": None, "plan": "", "row": None, "now": now}
    if now is None:
        return {"ok": False, "reason": "no_internet",
                "message_fa": _REASON_FA["no_internet"],
                "days_left": None, "plan": "", "row": None, "now": None}
    row = next((r for r in rows if r["username"] == user), None)
    if not row:
        return {"ok": False, "reason": "bad_user",
                "message_fa": _REASON_FA["bad_user"],
                "days_left": None, "plan": "", "row": None, "now": now}
    if (row.get("password") or "") != pwd:
        return {"ok": False, "reason": "bad_pass",
                "message_fa": _REASON_FA["bad_pass"],
                "days_left": None, "plan": row.get("plan") or "",
                "row": None, "now": now}
    if row.get("status") != "active":
        return {"ok": False, "reason": "disabled",
                "message_fa": _REASON_FA["disabled"],
                "days_left": days_left(row.get("expires") or "", now),
                "plan": row.get("plan") or "", "row": row, "now": now}
    left = days_left(row.get("expires") or "", now)
    if left is None:
        return {"ok": False, "reason": "bad_row",
                "message_fa": _REASON_FA["bad_row"],
                "days_left": None, "plan": row.get("plan") or "",
                "row": row, "now": now}
    if left < 0:
        return {"ok": False, "reason": "expired",
                "message_fa": _REASON_FA["expired"],
                "days_left": left, "plan": row.get("plan") or "",
                "row": row, "now": now}
    return {"ok": True, "reason": "ok", "message_fa": _REASON_FA["ok"],
            "days_left": left, "plan": row.get("plan") or "full",
            "row": row, "now": now,
            "full_name": ("%s %s" % (row.get("first_name") or "",
                                     row.get("last_name") or "")).strip()}
