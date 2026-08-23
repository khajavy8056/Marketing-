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
    created_at TEXT
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
    "watch_interval_sec": 300,
    "phone_delay_sec": 10,
    "search_delay_sec": 5,
    "search_page_delay_sec": 8,
    "jitter_sec": 4,
    "per_account_daily_limit": 60,
    "ip_daily_limit": 240,
    "cooldown_on_block_min": 30,
    "sms_provider": "none",          # none | melipayamak
    "sms_api_key": "",
    "sms_username": "",
    "sms_password": "",
    "sms_line_number": "",
    "sms_auto_on_new": False,        # پیش‌فرض خاموش
    "sms_daily_limit": 40,
}


def _con(db_path: str) -> sqlite3.Connection:
    con = connect(db_path)
    con.executescript(SCHEMA_EXTRA)
    return con


# ------------------------------------------------------------ کلمات کلیدی --
def keywords_list(db_path: str) -> List[Dict[str, Any]]:
    with _con(db_path) as con:
        rows = con.execute(
            "SELECT id, keyword, cities, active, created_at FROM keywords "
            "ORDER BY id DESC").fetchall()
    out = []
    for r in rows:
        out.append({"id": r["id"], "keyword": r["keyword"],
                    "cities": json.loads(r["cities"]) if r["cities"] else None,
                    "active": bool(r["active"]), "created_at": r["created_at"]})
    return out


def keywords_add(db_path: str, keyword: str,
                 cities: Optional[List[int]] = None) -> bool:
    """افزودن کلمه کلیدی؛ رشته‌ای با کاما را می‌پذیرد و چندتایی می‌کند."""
    added = False
    with _con(db_path) as con:
        for kw in [k.strip() for k in keyword.split(",") if k.strip()]:
            cur = con.execute(
                "INSERT OR IGNORE INTO keywords (keyword, cities, created_at) "
                "VALUES (?,?,?)",
                (kw, json.dumps(cities) if cities else None,
                 time.strftime("%Y-%m-%d %H:%M:%S")))
            added = added or cur.rowcount > 0
    return added


def keywords_delete(db_path: str, kw_id: int) -> None:
    with _con(db_path) as con:
        con.execute("DELETE FROM keywords WHERE id=?", (kw_id,))


def keywords_toggle(db_path: str, kw_id: int, active: bool) -> None:
    with _con(db_path) as con:
        con.execute("UPDATE keywords SET active=? WHERE id=?", (int(active), kw_id))


def keywords_active_specs(db_path: str) -> List[Dict[str, Any]]:
    """تبدیل کلمات فعال به ساختار ورودی مانیتور."""
    return [{"keyword": k["keyword"], "cities": k["cities"], "pages": 1}
            for k in keywords_list(db_path) if k["active"]]


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
                out[r["key"]] = (json.loads(cur) if isinstance(default, (int, float, bool))
                                 else cur)
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
                     "telegram_chat_id": s["telegram_chat_id"]}
    for k in ("sms_provider", "sms_api_key", "sms_username", "sms_password",
              "sms_line_number", "sms_auto_on_new", "sms_daily_limit"):
        cfg[k] = s[k]
    return cfg
