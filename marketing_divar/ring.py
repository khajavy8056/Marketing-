# -*- coding: utf-8 -*-
"""کشف آگهی رینگ — وب Flutter؛ در فاز اول از HTML/لینک /a/{id}."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from .categories import search_slug as platform_slug
from .cities import slug_for_platform
from .platforms import lead_token, listing_url
from .pricing import parse_toman

_AD = re.compile(r"https?://(?:www\.)?ring\.ir/a/([A-Za-z0-9_-]+)", re.I)
_AD_REL = re.compile(r"/a/([A-Za-z0-9_-]{4,})", re.I)
_TITLE_NEAR = re.compile(r"<[^>]+>([^<]{6,90})</")


def parse_listings(html: str) -> List[Dict[str, Any]]:
    posts, seen = [], set()
    text = html or ""

    def add(nid: str) -> None:
        if nid in seen or nid.lower() in ("home", "faq", "login", "about"):
            return
        seen.add(nid)
        token = lead_token("ring", nid)
        posts.append({
            "token": token,
            "native_id": nid,
            "platform": "ring",
            "title": nid.replace("-", " "),
            "subtitle": "",
            "url": listing_url("ring", nid),
            "has_chat": True,
        })

    for nid in _AD.findall(text):
        add(nid)
    for nid in _AD_REL.findall(text):
        add(nid)
    from .contact import parse_visible_phone
    for p in posts:
        nid = p.get("native_id") or ""
        i = text.find(nid)
        window = text[max(0, i - 400): i + 1000] if i >= 0 else text[:2000]
        price = parse_toman(window)
        if price:
            p["price"] = price
        ph = parse_visible_phone(window)
        if ph:
            p["phone"] = ph
        if "توافقی" in window:
            p["price_kind"] = "negotiable"
    return posts[:80]


def search_url(city_slug: str = "", category: str = "", query: str = "") -> str:
    url = "https://ring.ir/"
    bits = []
    if city_slug and city_slug not in ("iran", ""):
        bits.append("city=" + city_slug)
    if category:
        bits.append("cat=" + category)
    if query:
        bits.append("q=" + quote(query))
    if bits:
        url = "https://ring.ir/?" + "&".join(bits)
    return url


def search(client, query: str, cities=None, page: int = 1,
           category: Optional[str] = None) -> List[Dict[str, Any]]:
    base = str(getattr(client, "base", "") or "")
    if base and "divar.ir" not in base and "ring" not in base:
        return []
    city_id = None
    if isinstance(cities, (list, tuple)) and cities:
        city_id = cities[0]
    elif cities not in (None, "", []):
        city_id = cities
    city = slug_for_platform(city_id, "ring")
    cat = platform_slug(category, "ring")
    url = search_url(city, cat, query or "")
    try:
        r = client._fetch("GET", url, timeout=25,
                          headers={"Accept": "text/html", "Accept-Language": "fa-IR"})
    except Exception:
        return []
    if getattr(r, "status_code", 0) != 200:
        return []
    return parse_listings(getattr(r, "text", "") or "")
