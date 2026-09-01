# -*- coding: utf-8 -*-
"""شهرهای عمومی دیوار — همان اسلاگ /s/{شهر}/…

شناسه‌های ۱ تا ۴۳ ثابت ماندند. بقیه شهرهای مهم استان‌ها اضافه شدند.
انتخاب چند شهر در پنل با لیست شناسه پشتیبانی می‌شود.
"""

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
    # تهران و البرز
    {"id": 44, "slug": "rey", "title": "ری"},
    {"id": 45, "slug": "varamin", "title": "ورامین"},
    {"id": 46, "slug": "shahriar", "title": "شهریار"},
    {"id": 47, "slug": "malard", "title": "ملارد"},
    {"id": 48, "slug": "pakdasht", "title": "پاکدشت"},
    {"id": 49, "slug": "qods", "title": "قدس"},
    {"id": 50, "slug": "robat-karim", "title": "رباط‌کریم"},
    {"id": 51, "slug": "pardis", "title": "پردیس"},
    {"id": 52, "slug": "damavand", "title": "دماوند"},
    {"id": 53, "slug": "firuzkuh", "title": "فیروزکوه"},
    {"id": 54, "slug": "pishva", "title": "پیشوا"},
    {"id": 55, "slug": "qarchak", "title": "قرچک"},
    {"id": 56, "slug": "andisheh", "title": "اندیشه"},
    {"id": 57, "slug": "golestan", "title": "گلستان"},
    {"id": 58, "slug": "nasimshahr", "title": "نسیم‌شهر"},
    {"id": 59, "slug": "hashtgerd", "title": "هشتگرد"},
    {"id": 60, "slug": "nazarabad", "title": "نظرآباد"},
    {"id": 61, "slug": "savojbolagh", "title": "ساوجبلاغ"},
    {"id": 62, "slug": "fardis", "title": "فردیس"},
    {"id": 63, "slug": "mahdashat", "title": "محمدشهر"},
    # خراسان
    {"id": 64, "slug": "torbat-heydarieh", "title": "تربت حیدریه"},
    {"id": 65, "slug": "torbat-jam", "title": "تربت جام"},
    {"id": 66, "slug": "kashmar", "title": "کاشمر"},
    {"id": 67, "slug": "quchan", "title": "قوچان"},
    {"id": 68, "slug": "chenaran", "title": "چناران"},
    {"id": 69, "slug": "taybad", "title": "تایباد"},
    {"id": 70, "slug": "gonabad", "title": "گناباد"},
    {"id": 71, "slug": "neishabur", "title": "نیشابور-قدیم"},
    {"id": 72, "slug": "bojnurd", "title": "بجنورد"},
    {"id": 73, "slug": "shirvan", "title": "شیروان"},
    {"id": 74, "slug": "esfarayen", "title": "اسفراین"},
    {"id": 75, "slug": "birjand", "title": "بیرجند"},
    {"id": 76, "slug": "qaen", "title": "قائن"},
    {"id": 77, "slug": "ferdows", "title": "فردوس"},
    {"id": 78, "slug": "tabas", "title": "طبس"},
    # اصفهان و یزد
    {"id": 79, "slug": "najafabad", "title": "نجف‌آباد"},
    {"id": 80, "slug": "khomeini-shahr", "title": "خمینی‌شهر"},
    {"id": 81, "slug": "shahinshahr", "title": "شاهین‌شهر"},
    {"id": 82, "slug": "falavarjan", "title": "فلاورجان"},
    {"id": 83, "slug": "mobarakeh", "title": "مبارکه"},
    {"id": 84, "slug": "lenjan", "title": "لنجان"},
    {"id": 85, "slug": "ardakan", "title": "اردکان"},
    {"id": 86, "slug": "mehriz", "title": "مهریز"},
    {"id": 87, "slug": "meybod", "title": "میبد"},
    {"id": 88, "slug": "bafgh", "title": "بافق"},
    # فارس
    {"id": 89, "slug": "marvdasht", "title": "مرودشت"},
    {"id": 90, "slug": "kazerun", "title": "کازرون"},
    {"id": 91, "slug": "jahrom", "title": "جهرم"},
    {"id": 92, "slug": "fasa", "title": "فسا"},
    {"id": 93, "slug": "lar", "title": "لار"},
    {"id": 94, "slug": "darab", "title": "داراب"},
    {"id": 95, "slug": "abadeh", "title": "آباده"},
    {"id": 96, "slug": "neyriz", "title": "نی‌ریز"},
    # آذربایجان
    {"id": 97, "slug": "maragheh", "title": "مراغه"},
    {"id": 98, "slug": "marand", "title": "مرند"},
    {"id": 99, "slug": "ahar", "title": "اهر"},
    {"id": 100, "slug": "bonab", "title": "بناب"},
    {"id": 101, "slug": "miandoab", "title": "میاندوآب"},
    {"id": 102, "slug": "khoy", "title": "خوی"},
    {"id": 103, "slug": "mahabad", "title": "مهاباد"},
    {"id": 104, "slug": "bukan", "title": "بوکان"},
    {"id": 105, "slug": "salmas", "title": "سلماس"},
    {"id": 106, "slug": "naqadeh", "title": "نقده"},
    {"id": 107, "slug": "piranshahr", "title": "پیرانشهر"},
    {"id": 108, "slug": "oshnavieh", "title": "اشنویه"},
    # گیلان و مازندران و گلستان
    {"id": 109, "slug": "bandar-anzali", "title": "بندر انزلی"},
    {"id": 110, "slug": "lahijan", "title": "لاهیجان"},
    {"id": 111, "slug": "langarud", "title": "لنگرود"},
    {"id": 112, "slug": "rudsar", "title": "رودسر"},
    {"id": 113, "slug": "sowmeeh-sara", "title": "صومعه‌سرا"},
    {"id": 114, "slug": "tonekabon", "title": "تنکابن"},
    {"id": 115, "slug": "ramsar", "title": "رامسر"},
    {"id": 116, "slug": "chalus", "title": "چالوس"},
    {"id": 117, "slug": "nowshahr", "title": "نوشهر"},
    {"id": 118, "slug": "nur", "title": "نور"},
    {"id": 119, "slug": "mahmudabad", "title": "محمودآباد"},
    {"id": 120, "slug": "neka", "title": "نکا"},
    {"id": 121, "slug": "behshahr", "title": "بهشهر"},
    {"id": 122, "slug": "juybar", "title": "جویبار"},
    {"id": 123, "slug": "fereydunkenar", "title": "فریدونکنار"},
    {"id": 124, "slug": "gonbad-kavus", "title": "گنبد کاووس"},
    {"id": 125, "slug": "aliabad", "title": "علی‌آباد"},
    {"id": 126, "slug": "bandar-torkaman", "title": "بندر ترکمن"},
    {"id": 127, "slug": "kordkuy", "title": "کردکوی"},
    {"id": 128, "slug": "aq-qala", "title": "آق‌قلا"},
    # خوزستان
    {"id": 129, "slug": "khorramshahr", "title": "خرمشهر"},
    {"id": 130, "slug": "andimeshk", "title": "اندیمشک"},
    {"id": 131, "slug": "mahshahr", "title": "ماهشهر"},
    {"id": 132, "slug": "shushtar", "title": "شوشتر"},
    {"id": 133, "slug": "shush", "title": "شوش"},
    {"id": 134, "slug": "behbahan", "title": "بهبهان"},
    {"id": 135, "slug": "izeh", "title": "ایذه"},
    {"id": 136, "slug": "masjed-soleyman", "title": "مسجدسلیمان"},
    {"id": 137, "slug": "ramhormoz", "title": "رامهرمز"},
    # کرمان و هرمزگان و سیستان
    {"id": 138, "slug": "rafsanjan", "title": "رفسنجان"},
    {"id": 139, "slug": "sirjan", "title": "سیرجان"},
    {"id": 140, "slug": "jiroft", "title": "جیرفت"},
    {"id": 141, "slug": "bam", "title": "بم"},
    {"id": 142, "slug": "zarand", "title": "زرند"},
    {"id": 143, "slug": "minab", "title": "میناب"},
    {"id": 144, "slug": "bandar-lengeh", "title": "بندر لنگه"},
    {"id": 145, "slug": "qeshm-city", "title": "قشم شهر"},
    {"id": 146, "slug": "zabol", "title": "زابل"},
    {"id": 147, "slug": "iranshahr", "title": "ایرانشهر"},
    {"id": 148, "slug": "chabahar", "title": "چابهار"},
    {"id": 149, "slug": "konarak", "title": "کنارک"},
    # غرب و مرکز
    {"id": 150, "slug": "borujerd", "title": "بروجرد"},
    {"id": 151, "slug": "dorud", "title": "دورود"},
    {"id": 152, "slug": "aligudarz", "title": "الیگودرز"},
    {"id": 153, "slug": "coohdasht", "title": "کوهدشت"},
    {"id": 154, "slug": "malayer", "title": "ملایر"},
    {"id": 155, "slug": "nahavand", "title": "نهاوند"},
    {"id": 156, "slug": "tuyserkan", "title": "تویسرکان"},
    {"id": 157, "slug": "saveh", "title": "ساوه"},
    {"id": 158, "slug": "khomein", "title": "خمین"},
    {"id": 159, "slug": "mahallat", "title": "محلات"},
    {"id": 160, "slug": "saqqez", "title": "سقز"},
    {"id": 161, "slug": "marivan", "title": "مریوان"},
    {"id": 162, "slug": "baneh", "title": "بانه"},
    {"id": 163, "slug": "qorveh", "title": "قروه"},
    {"id": 164, "slug": "islamabad-gharb", "title": "اسلام‌آباد غرب"},
    {"id": 165, "slug": "dehloran", "title": "دهلران"},
    {"id": 166, "slug": "abhar", "title": "ابهر"},
    {"id": 167, "slug": "khorramdarreh", "title": "خرمدره"},
    {"id": 168, "slug": "takestan", "title": "تاکستان"},
    {"id": 169, "slug": "alvand", "title": "الوند"},
    {"id": 170, "slug": "parsabad", "title": "پارس‌آباد"},
    {"id": 171, "slug": "meshginshahr", "title": "مشگین‌شهر"},
    {"id": 172, "slug": "khalkhal", "title": "خلخال"},
    {"id": 173, "slug": "shahrud", "title": "شاهرود"},
    {"id": 174, "slug": "damghan", "title": "دامغان"},
    {"id": 175, "slug": "garmsar", "title": "گرمسار"},
    {"id": 176, "slug": "borujen", "title": "بروجن"},
    {"id": 177, "slug": "dogonbadan", "title": "دوگنبدان"},
    {"id": 178, "slug": "borazjan", "title": "برازجان"},
    {"id": 179, "slug": "ganaveh", "title": "گناوه"},
    {"id": 180, "slug": "asaluyeh", "title": "عسلویه"},
    {"id": 181, "slug": "kangan", "title": "کنگان"},
]

# شناسه و اسلاگ تکراری (بجنورد/بیرجند قبلاً بودند) را یکتا می‌کنیم
_seen_ids = set()
_seen_slugs = set()
_uniq: List[Dict[str, Any]] = []
for _c in CITIES:
    if _c["id"] in _seen_ids:
        continue
    if _c["slug"] and _c["slug"] in _seen_slugs:
        continue
    _seen_ids.add(_c["id"])
    if _c["slug"]:
        _seen_slugs.add(_c["slug"])
    _uniq.append(_c)
CITIES = _uniq

_BY_ID = {c["id"]: c for c in CITIES}
_BY_SLUG = {c["slug"]: c for c in CITIES if c["slug"]}

# اسلاگ شیپور اگر با دیوار فرق کند
_PLATFORM_SLUG = {
    "sheypoor": {
        "bandar-abbas": "bandarabbass",
        "khorramabad": "khoramabad",
        "shahrekord": "shahr-e-kord",
        "bandar-anzali": "anzali",
        "gonbad-kavus": "gonbad",
    },
}


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


def slug_for_platform(city_id: Any, platform: str = "divar") -> str:
    """اسلاگ شهر برای همان پلتفرم — اگر جدول نگاشت نداشت همان دیوار است."""
    base = slug_of(city_id)
    if base in ("", "iran"):
        return "iran"
    plat = str(platform or "divar").strip().lower()
    return (_PLATFORM_SLUG.get(plat) or {}).get(base, base)


def parse_city_ids(raw: Any) -> Optional[List[int]]:
    """ورودی پنل: None / [1,3] / '1,3' → لیست شناسه؛ خالی یعنی همه ایران."""
    if raw in (None, "", [], [0], ["0"]):
        return None
    if isinstance(raw, (int, float)):
        n = int(raw)
        return None if n == 0 else [n]
    out: List[int] = []
    seq = raw
    if isinstance(raw, str):
        seq = [p.strip() for p in raw.replace("،", ",").split(",") if p.strip()]
    for item in seq or []:
        try:
            n = int(item)
        except (TypeError, ValueError):
            continue
        if n and n not in out and n in _BY_ID:
            out.append(n)
    return out or None
