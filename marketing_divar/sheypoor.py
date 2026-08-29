# -*- coding: utf-8 -*-
"""کشف آگهی شیپور از HTML عمومی + پارس قیمت/وضعیت."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote, unquote

from .cities import slug_of
from .platforms import lead_token, listing_url
from .pricing import parse_toman

# /v/{slug}-{id}.html
_AD = re.compile(
    r"https?://(?:www\.)?sheypoor\.com/v/([A-Za-z0-9%_\u0600-\u06FF-]+)-(\d{5,})\.html",
    re.I,
)
_AD_REL = re.compile(r"/v/([A-Za-z0-9%_\u0600-\u06FF-]+)-(\d{5,})\.html", re.I)
_COND = re.compile(r"وضعیت\s*کالا[:\s]*([^\n<]{2,40})")


def category_slug(divar_slug: Optional[str]) -> str:
    """نگاشت درخت واحد به اسلاگ شیپور."""
    m = {
        "mobile-phones": "mobile-tablet",
        "mobile-tablet": "mobile-tablet",
        "tablet": "mobile-tablet",
        "light": "car",
        "vehicles": "vehicles",
        "motorcycles": "motorcycles",
        "real-estate": "real-estate",
        "apartment-sell": "houses-apartments-for-sale",
        "house-villa-sell": "villa-for-sale",
        "apartment-rent": "house-apartment-for-rent",
        "electronic-devices": "electronics",
        "computers": "laptop-computer",
        "laptops": "laptop-computer",
        "home-kitchen": "home",
        "furniture-wood": "furniture",
        "jobs": "jobs",
        "services": "services",
        "animals": "animals-pet",
    }
    s = (divar_slug or "").strip()
    return m.get(s, s)


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
        })

    for slug, nid in _AD.findall(text):
        add(slug, nid)
    for slug, nid in _AD_REL.findall(text):
        add(slug, nid)
    _enrich(text, posts)
    return posts[:80]


def _enrich(html: str, posts: List[Dict[str, Any]]) -> None:
    for p in posts:
        nid = p.get("native_id") or ""
        i = html.find(nid) if nid else -1
        window = html[max(0, i - 400): i + 1200] if i >= 0 else html[:2500]
        price = parse_toman(window)
        if price:
            p["price"] = price
        if "توافقی" in window or "قیمتتوافقی" in window.replace(" ", ""):
            p["price_kind"] = "negotiable"
            p["price"] = p.get("price") or 0
        m = _COND.search(window)
        if m:
            p["condition"] = m.group(1).strip()
            p["status_text"] = p["condition"]


def search(client, query: str, cities=None, page: int = 1,
           category: Optional[str] = None) -> List[Dict[str, Any]]:
    """از همان _fetch کلاینت دیوار روی دامنه شیپور (بدون لاگین)."""
    base = str(getattr(client, "base", "") or "")
    if base and "divar.ir" not in base and "sheypoor" not in base:
        return []  # شبیه‌ساز تست
    from .client import city_slug as divar_city
    city = divar_city(cities)
    cat = category_slug(category)
    url = search_url(city, cat, query or "")
    if page and page > 1:
        sep = "&" if "?" in url else "?"
        url = url + sep + "page=%s" % page
    r = client._fetch("GET", url, timeout=25,
                      headers={"Accept": "text/html", "Accept-Language": "fa-IR,fa;q=0.9"})
    if getattr(r, "status_code", 0) != 200:
        return []
    return parse_listings(getattr(r, "text", "") or "")
