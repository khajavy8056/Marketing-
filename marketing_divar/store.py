# -*- coding: utf-8 -*-
"""ذخیره‌سازی تنظیمات رابط وب — کلمات کلیدی، قالب‌های پیام، تنظیمات.

جدا از جدول‌های leads/quota در db.py؛ روی همان فایل SQLite.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from .db import connect

SCHEMA_EXTRA = """
CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT UNIQUE NOT NULL,
    cities TEXT,                -- 'null' = کل کشور، '[1,3]' = شهرهای خاص
    active INTEGER DEFAULT 1,
    created_at TEXT,
    category TEXT DEFAULT '',   -- اسلاگ دسته دیوار؛ خالی = همه دسته‌ها
    browse INTEGER DEFAULT 0    -- 1 = کل دسته بدون فیلتر عنوان
);
CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,      -- 'chat' | 'sms'
    name TEXT NOT NULL,
    text TEXT NOT NULL,
    is_default INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

# کلیدهای تنظیماتی که از رابط وب قابل تغییرند (نام/مقدار پیش‌فرض)
EDITABLE_SETTINGS: Dict[str, Any] = {
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "telegram_api_base": "",      # مثلاً http://127.0.0.1:8081 یا ورکر
    "telegram_proxy": "",         # http://... یا socks5://... اگر api.telegram.org فیلتر است
    "bale_bot_token": "",
    "bale_chat_id": "",
    "rubika_bot_token": "",
    "rubika_chat_id": "",
    "watch_interval_sec": 300,
    "phone_delay_sec": 45,
    "search_delay_sec": 5,
    "search_page_delay_sec": 8,
    "jitter_sec": 4,
    "per_account_daily_limit": 60,
    "adaptive_until_captcha": True,
    "ip_daily_limit": 240,
    "cooldown_on_block_min": 30,
    "sms_provider": "none",          # none | melipayamak
    "sms_api_key": "",
    "sms_username": "",
    "sms_password": "",
    "sms_line_number": "",
    "sms_auto_on_new": False,        # پیش‌فرض خاموش
    "sms_daily_limit": 40,
    "vip_telegram": True,            # هشدار ویژه در تلگرام
}


def _con(db_path: str) -> sqlite3.Connection:
    con = connect(db_path)
    con.executescript(SCHEMA_EXTRA)
    cols = {r[1] for r in con.execute("PRAGMA table_info(keywords)")}
    if "category" not in cols:
        con.execute("ALTER TABLE keywords ADD COLUMN category TEXT DEFAULT ''")
        con.commit()
        cols.add("category")
    if "browse" not in cols:
        con.execute("ALTER TABLE keywords ADD COLUMN browse INTEGER DEFAULT 0")
        con.commit()
        try:
            from .categories import CATEGORIES, title_of
            titles = {c["title"] for c in CATEGORIES}
            titles.add("موبایل و تبلت")
            for r in con.execute("SELECT id, keyword, category FROM keywords").fetchall():
                cat = (r["category"] or "") if "category" in r.keys() else ""
                kw = r["keyword"] or ""
                if cat and (not kw or kw in titles or kw == title_of(cat)):
                    con.execute("UPDATE keywords SET browse=1 WHERE id=?", (r["id"],))
            con.commit()
        except Exception:
            pass
        cols = {r[1] for r in con.execute("PRAGMA table_info(keywords)")}
    if "price_min" not in cols:
        con.execute("ALTER TABLE keywords ADD COLUMN price_min INTEGER DEFAULT 0")
        con.commit()
    if "price_max" not in cols:
        con.execute("ALTER TABLE keywords ADD COLUMN price_max INTEGER DEFAULT 0")
        con.commit()
    if "vip" not in cols:
        con.execute("ALTER TABLE keywords ADD COLUMN vip INTEGER DEFAULT 0")
        con.commit()
    _apply_factory_defaults_2123(con)
    return con


def _apply_factory_defaults_2123(con: sqlite3.Connection) -> None:
    """کارخانه قبلی ۱۲۹/۱۰ ثانیه یک‌بار به ۶۰/۴۵ می‌رود. مقدار سفارشی نمی‌سوزد."""
    try:
        if con.execute("SELECT 1 FROM settings WHERE key='defaults_2_1_23'").fetchone():
            return

        def _raw(key: str) -> str | None:
            row = con.execute(
                "SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            if row is None:
                return None
            return str(row["value"]).strip().strip('"')

        lim = _raw("per_account_daily_limit")
        if lim is None or lim in ("129", "129.0"):
            con.execute(
                "INSERT INTO settings (key, value) VALUES ('per_account_daily_limit', '60') "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value")
        delay = _raw("phone_delay_sec")
        if delay is None or delay in ("10", "10.0"):
            con.execute(
                "INSERT INTO settings (key, value) VALUES ('phone_delay_sec', '45') "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value")
        con.execute(
            "INSERT INTO settings (key, value) VALUES ('defaults_2_1_23', '1') "
            "ON CONFLICT(key) DO NOTHING")
        con.commit()
    except Exception:
        pass


# ------------------------------------------------------------ کلمات کلیدی --
def keywords_list(db_path: str) -> List[Dict[str, Any]]:
    from .categories import title_of
    with _con(db_path) as con:
        rows = con.execute(
            "SELECT id, keyword, cities, active, created_at, category, browse, "
            "price_min, price_max, vip FROM keywords "
            "ORDER BY id DESC").fetchall()
    from .cities import title_of_city
    out = []
    for r in rows:
        cat = ""
        browse = 0
        pmin = pmax = vip = 0
        try:
            if "category" in r.keys():
                cat = r["category"] or ""
            if "browse" in r.keys():
                browse = int(r["browse"] or 0)
            if "price_min" in r.keys():
                pmin = int(r["price_min"] or 0)
            if "price_max" in r.keys():
                pmax = int(r["price_max"] or 0)
            if "vip" in r.keys():
                vip = int(r["vip"] or 0)
        except Exception:
            cat, browse = cat, 0
        cities = json.loads(r["cities"]) if r["cities"] else None
        city_title = ""
        if cities:
            city_title = "، ".join(title_of_city(c) for c in cities)
        out.append({"id": r["id"], "keyword": r["keyword"],
                    "cities": cities,
                    "city_title": city_title or "همه ایران",
                    "active": bool(r["active"]), "created_at": r["created_at"],
                    "category": cat, "category_title": title_of(cat),
                    "browse": bool(browse),
                    "price_min": pmin, "price_max": pmax, "vip": bool(vip)})
    return out


def keywords_add(db_path: str, keyword: str,
                 cities: Optional[List[int]] = None,
                 category: str = "",
                 price_min: int = 0, price_max: int = 0,
                 vip: bool = False) -> bool:
    """افزودن کلمه و/یا دستهٔ دیوار.

    بدون کلمه + دسته = مرور کل دسته (عنوان آگهی مهم نیست).
    کلمه + دسته = جستجو داخل همان دسته سپس تطبیق عبارت.
    """
    from .categories import normalize_slug, title_of
    cat = normalize_slug(category)
    parts = [k.strip() for k in (keyword or "").split(",") if k.strip()]
    browse = 0
    if not parts:
        if not cat:
            return False
        parts = [title_of(cat)]
        browse = 1
    added = False
    pmin = int(price_min or 0)
    pmax = int(price_max or 0)
    vip_i = int(bool(vip))
    with _con(db_path) as con:
        for label in parts:
            cur = con.execute(
                "INSERT OR IGNORE INTO keywords "
                "(keyword, cities, created_at, category, browse, price_min, price_max, vip) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (label, json.dumps(cities) if cities else None,
                 time.strftime("%Y-%m-%d %H:%M:%S"), cat, browse, pmin, pmax, vip_i))
            added = added or cur.rowcount > 0
            if cur.rowcount == 0:
                con.execute(
                    "UPDATE keywords SET category=?, browse=?, cities=?, "
                    "price_min=?, price_max=?, vip=? WHERE keyword=?",
                    (cat, browse, json.dumps(cities) if cities else None,
                     pmin, pmax, vip_i, label))
                added = True
    return added


def keywords_delete(db_path: str, kw_id: int) -> None:
    with _con(db_path) as con:
        con.execute("DELETE FROM keywords WHERE id=?", (kw_id,))


def keywords_toggle(db_path: str, kw_id: int, active: bool) -> None:
    with _con(db_path) as con:
        con.execute("UPDATE keywords SET active=? WHERE id=?", (int(active), kw_id))


def keywords_active_specs(db_path: str) -> List[Dict[str, Any]]:
    """تبدیل کلمات فعال به ساختار ورودی مانیتور."""
    from .categories import title_of
    specs = []
    for k in keywords_list(db_path):
        if not k["active"]:
            continue
        cat = k.get("category") or ""
        from .categories import CATEGORIES
        titles = {c["title"] for c in CATEGORIES}
        titles.add("موبایل و تبلت")
        match_all = bool(k.get("browse")) or (
            bool(cat) and (not k["keyword"] or k["keyword"] in titles
                           or k["keyword"] == title_of(cat)))
        specs.append({"keyword": k["keyword"], "cities": k["cities"], "pages": 1,
                      "category": cat, "match_all": match_all,
                      "price_min": int(k.get("price_min") or 0),
                      "price_max": int(k.get("price_max") or 0),
                      "vip": bool(k.get("vip"))})
    return specs


# ------------------------------------------------------------ قالب پیام --
def template_get(db_path: str, channel: str) -> Optional[Dict[str, Any]]:
    with _con(db_path) as con:
        r = con.execute("SELECT id, name, text FROM templates "
                        "WHERE channel=? AND is_default=1", (channel,)).fetchone()
    if r:
        return {"id": r["id"], "name": r["name"], "text": r["text"]}
    return None


def template_set(db_path: str, channel: str, text: str,
                 name: str = "پیش‌فرض") -> None:
    with _con(db_path) as con:
        con.execute("UPDATE templates SET is_default=0 WHERE channel=?", (channel,))
        row = con.execute("SELECT id FROM templates WHERE channel=? AND name=?",
                          (channel, name)).fetchone()
        if row:
            con.execute("UPDATE templates SET text=?, is_default=1 WHERE id=?",
                        (text, row["id"]))
        else:
            con.execute(
                "INSERT INTO templates (channel, name, text, is_default) "
                "VALUES (?,?,?,1)", (channel, name, text))


# --------------------------------------------------------------- تنظیمات --
def settings_all(db_path: str) -> Dict[str, Any]:
    """تنظیمات ذخیره‌شده + پیش‌فرض‌ها."""
    out = dict(EDITABLE_SETTINGS)
    with _con(db_path) as con:
        for r in con.execute("SELECT key, value FROM settings").fetchall():
            if r["key"] in out:
                cur, default = r["value"], out[r["key"]]
                try:
                    out[r["key"]] = (json.loads(cur) if isinstance(default, (int, float, bool))
                                     else cur)
                except Exception:
                    out[r["key"]] = default
    return out


def settings_set(db_path: str, key: str, value: Any) -> bool:
    if key not in EDITABLE_SETTINGS:
        return False
    stored = json.dumps(value) if isinstance(value, (int, float, bool, list)) else value
    with _con(db_path) as con:
        con.execute("INSERT INTO settings (key, value) VALUES (?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, stored))
    return True


def effective_config(db_path: str, base_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """پیکربندی اجرایی = پیش‌فرض‌های config.json + تنظیمات وب (وب مقدم است)."""
    cfg = dict(base_cfg)
    s = settings_all(db_path)
    for k in ("watch_interval_sec", "phone_delay_sec", "per_account_daily_limit",
              "ip_daily_limit", "cooldown_on_block_min", "search_delay_sec",
              "search_page_delay_sec", "jitter_sec"):
        cfg[k] = s[k]
    cfg["notify"] = {"telegram_bot_token": s["telegram_bot_token"],
                     "telegram_chat_id": s["telegram_chat_id"],
                     "telegram_api_base": s.get("telegram_api_base") or "",
                     "telegram_proxy": s.get("telegram_proxy") or "",
                     "telegram_enabled": s.get("telegram_enabled", True),
                     "bale_bot_token": s.get("bale_bot_token") or "",
                     "bale_chat_id": s.get("bale_chat_id") or "",
                     "bale_enabled": s.get("bale_enabled", True),
                     "rubika_bot_token": s.get("rubika_bot_token") or "",
                     "rubika_chat_id": s.get("rubika_chat_id") or "",
                     "rubika_enabled": s.get("rubika_enabled", True)}
    for k in ("sms_provider", "sms_api_key", "sms_username", "sms_password",
              "sms_line_number", "sms_auto_on_new", "sms_daily_limit",
              "adaptive_until_captcha"):
        cfg[k] = s[k]
    return cfg
