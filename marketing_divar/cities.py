# -*- coding: utf-8 -*-
"""شهرهای عمومی دیوار — همان اسلاگ /s/{شهر}/…"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# idهایی که جامعه/API قدیمی می‌شناسند ثابت ماندند
CITIES: List[Dict[str, Any]] = [
    {"id": 0, "slug": "", "title": "همه ایران"},
    {"id": 1, "slug": "tehran", "title": "تهران"},
    {"id": 2, "slug": "karaj", "title": "کرج"},
    {"id": 3, "slug": "mashhad", "title": "مشهد"},
    {"id": 4, "slug": "isfahan", "title": "اصفهان"},
    {"id": 5, "slug": "shiraz", "title": "شیراز"},
    {"id": 6, "slug": "ahvaz", "title": "اهواز"},
    {"id": 7, "slug": "tabriz", "title": "تبریز"},
    {"id": 8, "slug": "qom", "title": "قم"},
    {"id": 9, "slug": "kermanshah", "title": "کرمانشاه"},
    {"id": 10, "slug": "urmia", "title": "ارومیه"},
    {"id": 11, "slug": "rasht", "title": "رشت"},
    {"id": 12, "slug": "zahedan", "title": "زاهدان"},
    {"id": 13, "slug": "hamadan", "title": "همدان"},
    {"id": 14, "slug": "kerman", "title": "کرمان"},
    {"id": 15, "slug": "yazd", "title": "یزد"},
    {"id": 16, "slug": "ardabil", "title": "اردبیل"},
    {"id": 17, "slug": "bandar-abbas", "title": "بندرعباس"},
    {"id": 18, "slug": "arak", "title": "اراک"},
    {"id": 19, "slug": "qazvin", "title": "قزوین"},
    {"id": 20, "slug": "zanjan", "title": "زنجان"},
    {"id": 21, "slug": "sanandaj", "title": "سنندج"},
    {"id": 22, "slug": "khorramabad", "title": "خرم‌آباد"},
    {"id": 23, "slug": "gorgan", "title": "گرگان"},
    {"id": 24, "slug": "sari", "title": "ساری"},
    {"id": 25, "slug": "bushehr", "title": "بوشهر"},
    {"id": 26, "slug": "birjand", "title": "بیرجند"},
    {"id": 27, "slug": "bojnurd", "title": "بجنورد"},
    {"id": 28, "slug": "ilam", "title": "ایلام"},
    {"id": 29, "slug": "yasuj", "title": "یاسوج"},
    {"id": 30, "slug": "shahrekord", "title": "شهرکرد"},
    {"id": 31, "slug": "semnan", "title": "سمنان"},
    {"id": 32, "slug": "kashan", "title": "کاشان"},
    {"id": 33, "slug": "kish", "title": "کیش"},
    {"id": 34, "slug": "qeshm", "title": "قشم"},
    {"id": 35, "slug": "islamshahr", "title": "اسلامشهر"},
    {"id": 36, "slug": "nishabur", "title": "نیشابور"},
    {"id": 37, "slug": "sabzevar", "title": "سبزوار"},
    {"id": 38, "slug": "dezful", "title": "دزفول"},
    {"id": 39, "slug": "abadan", "title": "آبادان"},
    {"id": 40, "slug": "amol", "title": "آمل"},
    {"id": 41, "slug": "babol", "title": "بابل"},
    {"id": 42, "slug": "qaemshahr", "title": "قائم‌شهر"},
    {"id": 43, "slug": "babolsar", "title": "بابلسر"},
]

_BY_ID = {c["id"]: c for c in CITIES}
_BY_SLUG = {c["slug"]: c for c in CITIES if c["slug"]}


def public_list() -> List[Dict[str, Any]]:
    return [dict(c) for c in CITIES]


def slug_of(city_id: Any) -> str:
    if city_id in (None, "", 0, "0"):
        return "iran"
    if isinstance(city_id, str) and not city_id.isdigit():
        s = city_id.strip().lower()
        return s if s in _BY_SLUG or s == "iran" else "iran"
    try:
        n = int(city_id)
    except (TypeError, ValueError):
        return "iran"
    c = _BY_ID.get(n)
    return c["slug"] if c and c["slug"] else "iran"


def title_of_city(city_id: Any) -> str:
    try:
        n = int(city_id)
    except (TypeError, ValueError):
        return str(city_id or "")
    c = _BY_ID.get(n)
    return c["title"] if c else str(city_id)
