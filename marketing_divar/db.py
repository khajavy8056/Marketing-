# -*- coding: utf-8 -*-
"""دیتابیس سرنخ‌ها — SQLite سبک و بدون وابستگی خارجی.

جدول leads هر آگهی/سرنخ را یک بار ذخیره می‌کند (یکتا بر اساس توکن) و
وضعیت شماره تماس و پیگیری تماس را نگه می‌دارد.
"""

from __future__ import annotations

import csv
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT UNIQUE NOT NULL,
    title TEXT,
    subtitle TEXT,
    url TEXT,
    keyword TEXT,
    city TEXT,
    has_chat INTEGER DEFAULT 0,
    phone TEXT,
    phone_status TEXT DEFAULT 'pending',  -- pending|found|hidden|error
    phone_error TEXT,
    lead_status TEXT DEFAULT 'new',       -- new|contacted|replied|converted|ignored
    notes TEXT,
    first_seen_at TEXT,
    phone_checked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone);
CREATE INDEX IF NOT EXISTS idx_leads_keyword ON leads(keyword);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT, city TEXT, pages INTEGER,
    posts_seen INTEGER, new_posts INTEGER,
    phones_found INTEGER, phones_hidden INTEGER, errors INTEGER,
    started_at TEXT, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS quota (
    day TEXT PRIMARY KEY,
    phones INTEGER DEFAULT 0,
    searches INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS quota_accounts (
    day TEXT,
    account TEXT,
    phones INTEGER DEFAULT 0,
    PRIMARY KEY (day, account)
);
"""


def account_quota_today(con: sqlite3.Connection, account: str) -> int:
    row = con.execute("SELECT phones FROM quota_accounts WHERE day=? AND account=?",
                      (time.strftime("%Y-%m-%d"), account)).fetchone()
    return row["phones"] if row else 0


def bump_account_quota(con: sqlite3.Connection, account: str) -> int:
    day = time.strftime("%Y-%m-%d")
    con.execute("INSERT INTO quota_accounts (day, account, phones) VALUES (?,?,0) "
                "ON CONFLICT(day, account) DO NOTHING", (day, account))
    con.execute("UPDATE quota_accounts SET phones = phones + 1 "
                "WHERE day=? AND account=?", (day, account))
    con.commit()
    return account_quota_today(con, account)


def chat_queue(con: sqlite3.Connection, keyword: Optional[str] = None,
               limit: int = 0) -> List[sqlite3.Row]:
    """سرنخ‌های «فقط چت» که هنوز پیام نگرفته‌اند — لیست کار بخش پیام."""
    q = ("SELECT * FROM leads WHERE phone_status='hidden' AND lead_status='new' "
         "ORDER BY id DESC")
    args: List[Any] = []
    if keyword:
        q = q.replace("ORDER BY", "AND keyword=? ORDER BY")
        args.append(keyword)
    rows = con.execute(q, args).fetchall()
    return rows[:limit] if limit > 0 else rows


def quota_today(con: sqlite3.Connection) -> Dict[str, int]:
    row = con.execute("SELECT phones, searches FROM quota WHERE day=?",
                      (time.strftime("%Y-%m-%d"),)).fetchone()
    return {"phones": row["phones"] if row else 0,
            "searches": row["searches"] if row else 0}


def bump_quota(con: sqlite3.Connection, field: str, by: int = 1) -> int:
    """افزایش شمارنده روزانه؛ مقدار جدید را برمی‌گرداند."""
    assert field in ("phones", "searches")
    day = time.strftime("%Y-%m-%d")
    con.execute("INSERT INTO quota (day) VALUES (?) "
                "ON CONFLICT(day) DO NOTHING", (day,))
    cur = con.execute(f"UPDATE quota SET {field} = {field} + ? WHERE day=?",
                      (by, day))
    con.commit()
    return quota_today(con)[field]


def connect(db_path: str = "data/divar_leads.db") -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def upsert_lead(con: sqlite3.Connection, post: Dict[str, Any],
                keyword: str, city: str) -> bool:
    """درج سرنخ جدید؛ اگر توکن قبلاً بوده، چیزی تغییر نمی‌کند. True = جدید."""
    cur = con.execute(
        "INSERT OR IGNORE INTO leads "
        "(token, title, subtitle, url, keyword, city, has_chat, first_seen_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (post["token"], post.get("title"), post.get("subtitle"),
         post.get("url"), keyword, str(city), int(bool(post.get("has_chat"))), now()))
    return cur.rowcount > 0


def pending_phone(con: sqlite3.Connection, keyword: Optional[str] = None,
                  limit: int = 0, newest_first: bool = False) -> List[sqlite3.Row]:
    """صف سرنخ‌های بدون شماره؛ پیش‌فرض قدیمی‌ترین اول (مانیتور: جدیدترین اول)."""
    q = "SELECT * FROM leads WHERE phone_status='pending'"
    args: List[Any] = []
    if keyword:
        q += " AND keyword=?"
        args.append(keyword)
    q += " ORDER BY id DESC" if newest_first else " ORDER BY id"
    if limit > 0:
        q += " LIMIT ?"
        args.append(limit)
    return con.execute(q, args).fetchall()


def set_phone(con: sqlite3.Connection, token: str, result: Dict[str, Any]) -> None:
    status = result.get("status", "error")
    con.execute(
        "UPDATE leads SET phone=?, phone_status=?, phone_error=?, phone_checked_at=? "
        "WHERE token=?",
        (result.get("phone"), status, result.get("message", ""), now(), token))


def set_lead_status(con: sqlite3.Connection, token: str, status: str,
                    notes: str = "") -> None:
    con.execute("UPDATE leads SET lead_status=?, notes=? WHERE token=?",
                (status, notes, token))


def log_run(con: sqlite3.Connection, **kw: Any) -> None:
    con.execute(
        "INSERT INTO runs (keyword, city, pages, posts_seen, new_posts, "
        "phones_found, phones_hidden, errors, started_at, finished_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (kw.get("keyword"), kw.get("city"), kw.get("pages"), kw.get("posts_seen"),
         kw.get("new_posts"), kw.get("phones_found"), kw.get("phones_hidden"),
         kw.get("errors"), kw.get("started_at"), now()))


def stats(con: sqlite3.Connection) -> List[sqlite3.Row]:
    return con.execute("""
        SELECT keyword, COUNT(*) AS total,
               SUM(phone_status='found')  AS with_phone,
               SUM(phone_status='hidden') AS hidden_phone,
               SUM(phone_status='pending') AS pending,
               SUM(phone_status='error')  AS errors,
               SUM(lead_status='contacted') AS contacted
        FROM leads GROUP BY keyword ORDER BY total DESC
    """).fetchall()


def export_csv(con: sqlite3.Connection, path: str,
               only_with_phone: bool = False) -> int:
    q = ("SELECT token, title, subtitle, phone, phone_status, keyword, city, "
         "lead_status, url, first_seen_at FROM leads")
    if only_with_phone:
        q += " WHERE phone_status='found'"
    q += " ORDER BY id DESC"
    rows = con.execute(q).fetchall()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig برای اکسل
        w = csv.writer(f)
        w.writerow(["token", "title", "subtitle", "phone", "phone_status",
                    "keyword", "city", "lead_status", "url", "first_seen_at"])
        for r in rows:
            w.writerow(list(r))
    return len(rows)
