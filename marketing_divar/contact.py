# -*- coding: utf-8 -*-
"""شماره تماس هر پلتفرم از مسیر همان سایت.

دیوار: API لاگین‌شده. شیپور و رینگ: کلیک «نمایش شماره» در همان پروفایل Chromium.
اگر شماره باشد پیامک؛ اگر صریحاً فقط‌چت باشد چت.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, Optional

from .client import normalize_phone
from .platforms import listing_url, split_token

_PHONE_RE = re.compile(r"(?<!\d)(09\d{9})(?!\d)")
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_HIDDEN = (
    "فقط چت", "شماره مخفی", "از طریق چت", "شماره تماس مخفی",
    "چت کنید", "امکان نمایش شماره نیست",
)
_GONE = (
    "آگهی حذف شده", "این آگهی حذف شده", "آگهی مورد نظر یافت نشد",
    "دیگر در دسترس نیست", "این آگهی وجود ندارد",
)


def parse_visible_phone(text: str) -> Optional[str]:
    blob = (text or "").translate(_FA_DIGITS)
    for m in _PHONE_RE.findall(blob):
        p = normalize_phone(m)
        if p and p.startswith("09") and len(p) == 11:
            return p
    return None


def classify_listing_html(html: str, platform: str = "divar") -> Dict[str, Any]:
    t = html or ""
    if any(m in t for m in _GONE):
        return {"status": "removed", "message": "آگهی حذف شده",
                "platform": platform}
    phone = parse_visible_phone(t)
    if phone:
        return {"status": "found", "phone": phone, "platform": platform}
    if any(m in t for m in _HIDDEN):
        return {"status": "hidden", "message": "explicit_hidden",
                "platform": platform}
    return {"status": "error",
            "message": "شماره در صفحه نبود — در صف شماره ماند",
            "platform": platform}


def _js_reveal(platform: str) -> str:
    labels = {
        "sheypoor": ["نمایش شماره", "تماس", "شماره تماس", "تماس بگیرید",
                     "مشاهده شماره", "Call"],
        "ring": ["نمایش شماره", "تماس", "شماره", "تماس بگیرید", "Call"],
        "divar": ["نمایش شماره", "شماره تماس", "تماس", "اطلاعات تماس"],
    }.get(platform, ["نمایش شماره", "تماس", "شماره تماس"])
    import json
    return """(async () => {
      const labels = %s;
      const nodes = Array.from(document.querySelectorAll('button,a,[role=button],span'));
      let btn = nodes.find(el => labels.some(t => (el.innerText||'').trim().includes(t)));
      if (btn) { btn.click(); await new Promise(r => setTimeout(r, 1100)); }
      const t = ((document.body && document.body.innerText) || '') + ' ' + document.title;
      return {text: t.slice(0, 8000), href: location.href, title: document.title||''};
    })()""" % json.dumps(labels, ensure_ascii=False)


def reveal_via_browser(url: str, accounts_dir: str, account: str,
                       token: str = "", platform: str = "") -> Dict[str, Any]:
    from .chat_browser import _cdp_eval, _connect_profile, _js_gone_check, _profile_lock
    plat = platform or split_token(token)[0]
    if not accounts_dir or not account:
        return {"status": "error", "platform": plat,
                "message": "پروفایل Chromium برای شماره مشخص نیست"}
    lock = _profile_lock(account)
    if not lock.acquire(timeout=90):
        return {"status": "error", "platform": plat,
                "message": "پروفایل مشغول است — بعداً"}
    cdp = None
    try:
        import time
        cdp, _port = _connect_profile(accounts_dir, account)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Page.navigate", {"url": url}, timeout=25)
        time.sleep(2.2)
        gone = _cdp_eval(cdp, _js_gone_check(), timeout=8)
        if isinstance(gone, dict) and gone.get("gone"):
            return {"status": "removed", "platform": plat,
                    "message": "آگهی حذف شده"}
        res = _cdp_eval(cdp, _js_reveal(plat), timeout=20)
        text = ""
        if isinstance(res, dict):
            text = str(res.get("text") or "")
        return classify_listing_html(text, plat)
    except Exception as e:
        return {"status": "error", "platform": plat, "message": str(e)[:200]}
    finally:
        try:
            if cdp:
                cdp.close()
        except Exception:
            pass
        lock.release()


def get_contact(token: str, client: Any = None, accounts_dir: str = "",
                account: str = "", url: str = "",
                reveal_fn: Optional[Callable] = None) -> Dict[str, Any]:
    """شماره این آگهی را از مسیر همان پلتفرم می‌گیرد."""
    plat, nid = split_token(token)
    dest = url or listing_url(plat, nid)
    if plat == "divar" and client is not None and reveal_fn is None:
        from .client import DivarAuthError
        try:
            res = client.get_phone(nid)
        except DivarAuthError:
            if accounts_dir and account:
                res = reveal_via_browser(dest, accounts_dir, account,
                                         token=token, platform=plat)
            else:
                raise
        if isinstance(res, dict):
            res.setdefault("platform", "divar")
        return res
    if reveal_fn is not None:
        out = reveal_fn(dest, plat, nid)
        if isinstance(out, dict):
            out.setdefault("platform", plat)
            return out
        return {"status": "error", "platform": plat, "message": str(out)}
    return reveal_via_browser(dest, accounts_dir, account,
                              token=token, platform=plat)
