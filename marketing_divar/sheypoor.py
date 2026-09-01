# -*- coding: utf-8 -*-
"""شیپور — کامل مثل دیوار.

- جستجو از HTML عمومی + پارس قیمت/وضعیت/شهر
- دسته‌بندی نگاشت از درخت واحد
- شهر نگاشت
- شماره: کلیک «نمایش شماره» در Chromium همان پروفایل (contact.py)
- چت: همان مسیر دیوار (chat_browser.py) با لیبل‌های شیپور

وقتی دیوار و شیپور هر دو فعال باشند، مانیتور هر دو را می‌گردد.
لاگین شیپور مثل دیوار: تب دوم همان پروفایل Chromium (chromium_profile.py)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote, unquote

from .categories import search_slug as platform_slug
from .cities import slug_for_platform
from .platforms import lead_token, listing_url
from .pricing import parse_toman

# الگوهای لینک آگهی شیپور
_AD = re.compile(
    r"https?://(?:www\.)?sheypoor\.com/v/([A-Za-z0-9%_\u0600-\u06FF-]+)-(\d{5,})\.html",
    re.I,
)
_AD_REL = re.compile(r"/v/([A-Za-z0-9%_\u0600-\u06FF-]+)-(\d{5,})\.html", re.I)

# وضعیت کالا
_COND = re.compile(r"وضعیت\s*کالا[:\s]*([^\n<]{2,40})")
_PRICE_KIND_NEG = re.compile(r"توافقی|قیمت\s*توافقی", re.I)


def category_slug(divar_slug: Optional[str]) -> str:
    return platform_slug(divar_slug, "sheypoor")


def search_url(city_slug: str, category: str = "", query: str = "") -> str:
    city = city_slug or "tehran"
    if city in ("iran", ""):
        city = "iran"
    path = "https://www.sheypoor.com/s/%s" % city
    if category:
        path += "/" + category
    if query:
        path += "?q=" + quote(query)
    return path


def parse_listings(html: str) -> List[Dict[str, Any]]:
    posts, seen = [], set()
    text = html or ""

    def add(slug: str, nid: str) -> None:
        if nid in seen:
            return
        seen.add(nid)
        title = unquote(slug).replace("-", " ").strip()
        token = lead_token("sheypoor", nid)
        posts.append({
            "token": token,
            "native_id": nid,
            "platform": "sheypoor",
            "title": title,
            "subtitle": "",
            "url": listing_url("sheypoor", nid, slug),
            "has_chat": True,
            "has_phone": True,  # شیپور هم شماره دارد
        })

    for slug, nid in _AD.findall(text):
        add(slug, nid)
    for slug, nid in _AD_REL.findall(text):
        add(slug, nid)
    _enrich(text, posts)
    return posts[:80]


_TITLE_NEAR = re.compile(r"<[^>]+>([^<]{6,120})</")
_PRICE_NEAR = re.compile(r"(\d{1,3}(?:[,\s]\d{3})+|\d{7,})\s*(?:تومان|ریال)?", re.I)


def _enrich(html: str, posts: List[Dict[str, Any]]) -> None:
    from .contact import parse_visible_phone

    for p in posts:
        nid = p.get("native_id") or ""
        i = html.find(nid) if nid else -1
        window = html[max(0, i - 600): i + 1800] if i >= 0 else html[:4000]

        # قیمت
        price = parse_toman(window)
        if price:
            p["price"] = price
        # توافقی
        if _PRICE_KIND_NEG.search(window):
            p["price_kind"] = "negotiable"
            if not p.get("price"):
                p["price"] = 0

        # وضعیت
        m = _COND.search(window)
        if m:
            cond = m.group(1).strip()
            p["condition"] = cond
            p["status_text"] = cond

        # شماره اگر در HTML باشد
        ph = parse_visible_phone(window)
        if ph:
            p["phone"] = ph

        # عنوان بهتر
        # نزدیک‌ترین تگ متنی
        if i >= 0:
            snippet = html[max(0, i - 300): i + 300]
            tm = _TITLE_NEAR.search(snippet)
            if tm:
                cand = tm.group(1).strip()
                if cand and "sheypoor" not in cand.lower() and len(cand) > 5 and len(cand) < 100:
                    # اگر عنوان فعلی فقط اسلاگ بود، جایگزین کن
                    if p.get("title") and "-" in p["title"] or len(p.get("title") or "") < 6:
                        p["title"] = cand
                    elif not p.get("title"):
                        p["title"] = cand


def search(client, query: str, cities=None, page: int = 1,
           category: Optional[str] = None) -> List[Dict[str, Any]]:
    """جستجو روی شیپور — کامل مثل دیوار، با دسته و شهر و صفحه"""
    base = str(getattr(client, "base", "") or "")
    # اگر کلاینت تستی با base خاص است، اجازه بده
    if base and "divar.ir" not in base and "sheypoor" not in base and "test" not in base.lower():
        # اگر base دیوار نیست ولی تست نیست، همچنان سعی کن (چون anon client base دیوار دارد)
        # فقط اگر base شامل ring باشد، skip نکن چون anon base دیوار دارد
            pass
        # در حالت عادی anon base دیوار است، پس باید اجازه بده
        if "divar.ir" not in base and "sheypoor.com" not in base and "api" not in base:
            # برای تست‌های unit که base تستی دارند
            if not base.startswith("http"):
                return []

    city_id = None
    if isinstance(cities, (list, tuple)) and cities:
        city_id = cities[0]
    elif cities not in (None, "", []):
        city_id = cities
    city = slug_for_platform(city_id, "sheypoor")
    cat = category_slug(category)
    url = search_url(city, cat, query or "")
    if page and page > 1:
        sep = "&" if "?" in url else "?"
        url = url + sep + "page=%s" % page

    try:
        r = client._fetch("GET", url, timeout=25,
                          headers={
                              "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                              "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
                              "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                          })
    except Exception:
        return []
    if getattr(r, "status_code", 0) != 200:
        return []
    html = getattr(r, "text", "") or ""
    if not html:
        return []
    return parse_listings(html)


def login_url() -> str:
    return "https://www.sheypoor.com/session"


def is_logged_in_html(html: str) -> bool:
    """آیا HTML نشان می‌دهد کاربر لاگین است؟"""
    if not html:
        return False
    low = html.lower()
    # اگر دکمه ورود نباشد و پروفایل/خروج باشد
    if "خروج" in html and ("پروفایل" in html or "حساب کاربری" in html):
        return True
    if "my-account" in low or "dashboard" in low:
        return True
    # اگر فرم ورود دیده شود، لاگین نیست
    if 'name="phone"' in low and 'ورود' in html:
        return False
    return False


# برای سازگاری با monitor که هر دو پلتفرم را یکسان صدا می‌زند
def search_with_category(client, query: str, cities=None, page: int = 1,
                         category: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]:
    return search(client, query, cities=cities, page=page, category=category)
