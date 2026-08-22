# -*- coding: utf-8 -*-
"""جمع‌آور: جستجوی کلمه‌کلیدی → ذخیره سرنخ‌های جدید → دریافت شماره تماس."""

from __future__ import annotations

import sqlite3
import sys
from typing import Any, Dict, List, Optional

from .client import DivarAuthError, DivarClient
from .db import (connect, log_run, pending_phone, set_phone, upsert_lead)

CITY_NAMES = {1: "tehran", 2: "karaj", 3: "mashhad", 4: "isfahan"}


def pretty(name: Any) -> str:
    if isinstance(name, int) and name in CITY_NAMES:
        return CITY_NAMES[name]
    return str(name)


def run_collection(keyword: str, cities: Optional[List[int]] = None,
                   pages: int = 1, delay: float = 3.0, max_phones: int = 0,
                   no_phone: bool = False, db_path: str = "data/divar_leads.db",
                   client: Optional[DivarClient] = None,
                   on_auth_error=None) -> Dict[str, int]:
    """یک دور کامل جمع‌آوری برای یک کلمه‌کلیدی.

    on_auth_error: callback‌ی که اگر توکن منقضی شد صدا زده می‌شود
    (مثلاً برای لاگین تعاملی مجدد). اگر None باشد، اجرا متوقف می‌شود.
    """
    con = connect(db_path)
    cl = client or DivarClient()
    started = __import__("time").strftime("%Y-%m-%d %H:%M:%S")
    counters = {"posts_seen": 0, "new_posts": 0, "phones_found": 0,
                "phones_hidden": 0, "errors": 0}

    # ۱) جستجو و ذخیره سرنخ‌های جدید
    for page in range(1, pages + 1):
        if page > 1:
            cl.polite_sleep(delay)
        try:
            posts = cl.search(keyword, cities=cities, page=page)
        except Exception as e:
            print(f"[!] خطا در صفحه {page}: {e}")
            break
        if not posts:
            print(f"[*] صفحه {page}: نتیجه‌ای نبود — پایان نتایج")
            break
        new_in_page = 0
        for p in posts:
            counters["posts_seen"] += 1
            if upsert_lead(con, p, keyword, ",".join(pretty(c) for c in cities) if cities else "iran"):
                counters["new_posts"] += 1
                new_in_page += 1
        con.commit()
        print(f"[*] صفحه {page}: {len(posts)} آگهی ({new_in_page} جدید)")
        if new_in_page == 0 and page >= 2:
            break  # صفحه‌های بعدی همه تکراری‌اند

    # ۲) دریافت شماره برای سرنخ‌های بدون بررسی
    if no_phone:
        log_run(con, keyword=keyword, city=str(cities), pages=pages, **counters,
                started_at=started)
        con.commit()
        con.close()
        return counters

    if not cl.is_logged_in():
        if on_auth_error:
            on_auth_error()
        else:
            print("[!] برای گرفتن شماره باید لاگین کنید (فرمان login). "
                  "فعلاً فقط آگهی‌ها ذخیره شدند.")

    targets = pending_phone(con, keyword)
    if max_phones > 0:
        targets = targets[:max_phones]
    if targets:
        print(f"[*] دریافت شماره برای {len(targets)} سرنخ (تاخیر {delay:.0f}s بین درخواست‌ها)…")
    for i, row in enumerate(targets, 1):
        if cl.is_logged_in():
            try:
                cl.polite_sleep(delay)
                res = cl.get_phone(row["token"])
            except DivarAuthError as e:
                print(f"[!] {e}")
                if on_auth_error:
                    on_auth_error()
                    try:
                        res = cl.get_phone(row["token"])
                    except Exception as e2:
                        res = {"status": "error", "message": str(e2)}
                else:
                    break
            except Exception as e:
                res = {"status": "error", "message": str(e)}
        else:
            break  # بدون لاگین، ادامه نمی‌دهیم
        set_phone(con, row["token"], res)
        con.commit()
        st = res["status"]
        if st == "found":
            counters["phones_found"] += 1
            print(f"  [{i}/{len(targets)}] ✓ {row['title'][:35]} → {res['phone']}")
        elif st == "hidden":
            counters["phones_hidden"] += 1
            print(f"  [{i}/{len(targets)}] − {row['title'][:35]} → فقط چت")
        else:
            counters["errors"] += 1
            print(f"  [{i}/{len(targets)}] ✗ {row['title'][:35]} → {res.get('message','')[:60]}")

    log_run(con, keyword=keyword, city=str(cities), pages=pages, **counters,
            started_at=started)
    con.commit()
    con.close()
    return counters
