# -*- coding: utf-8 -*-
"""جمع‌آور: جستجو → سرنخ جدید → شماره تماس؛ مجهز به سهمیه روزانه،
قطع‌کننده مدار (Circuit Breaker) و مدیریت کپچای انسان-در-حلقه.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from .client import DivarAuthError, DivarBlockedError, DivarClient
from .db import (bump_quota, connect, log_run, pending_phone, quota_today,
                 set_phone, upsert_lead)
from .notifier import notify
from .rate import CircuitBreaker, RateLimiter

CITY_NAMES = {1: "tehran", 2: "karaj", 3: "mashhad", 4: "isfahan"}


def _pretty(city: Any) -> str:
    return CITY_NAMES.get(city, str(city)) if isinstance(city, int) else str(city)


def _handle_block(cfg: Dict[str, Any], breaker: CircuitBreaker,
                  err: DivarBlockedError) -> str:
    """سیاست برخورد با بلاک/کپچا: توقف، اعلان، حل انسانی اختیاری، بازگشت کند.

    خروجی: "resumed" (ادامه) یا "fatal" (توقف تا روز بعد)
    """
    seconds = breaker.trip(str(err))
    notify(cfg, f"دیوار محدود کرد: {err} (وضعیت {err.status}). "
                f"سرد شدن {int(seconds // 60)} دقیقه؛ پشت‌سرهم: {breaker.consecutive}")
    if breaker.is_fatal():
        notify(cfg, "سه بلاک پیاپی — اجرای امروز همین‌جا تمام می‌شود "
                    "(محافظ اکانت شماست). فردا با سرعت عادی ادامه دهید.")
        return "fatal"
    if cfg.get("interactive", True):
        try:
            input("\n[i] اگر کپچا/محدودیت در مرورگر هم دارید، با لاگین همان اکانت در "
                  "divar.ir آن را حل کنید، سپس Enter بزنید تا ادامه دهیم…")
            breaker.reset()  # اپراتور حل کرد
            return "resumed"
        except EOFError:  # محیط غیرتعاملی (سرور)
            pass
    print(f"[i] حالت غیرتعاملی: {int(seconds // 60)} دقیقه صبر می‌کنیم…")
    breaker.wait_cooldown(on_tick=lambda s: print(f"    … {s // 60 + 1} دقیقه مانده",
                                                  end="\r"))
    print()
    return "resumed"


def run_collection(keyword: str, cities: Optional[List[int]] = None,
                   pages: int = 1, max_phones: int = 0, no_phone: bool = False,
                   db_path: str = "data/divar_leads.db",
                   cfg: Optional[Dict[str, Any]] = None,
                   client: Optional[DivarClient] = None,
                   on_auth_error: Optional[Callable[[], None]] = None,
                   ) -> Dict[str, int]:
    """یک دور جمع‌آوری برای یک کلمه‌کلیدی (فقط موارد جدید شماره‌گیری می‌شوند)."""
    cfg = cfg or {}
    con = connect(db_path)
    limiter = RateLimiter(
        phone_delay=cfg.get("phone_delay_sec", 10),
        search_delay=cfg.get("search_delay_sec", 5),
        page_delay=cfg.get("search_page_delay_sec", 8),
        jitter=cfg.get("jitter_sec", 4))
    breaker = CircuitBreaker(
        cooldown_min=cfg.get("cooldown_on_block_min", 30),
        backoff_mult=cfg.get("backoff_multiplier", 1.5),
        max_consecutive=cfg.get("max_consecutive_blocks", 3))
    cl = client or DivarClient(limiter=limiter)
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    counters = {"posts_seen": 0, "new_posts": 0, "phones_found": 0,
                "phones_hidden": 0, "errors": 0}

    def ensure_login() -> bool:
        if cl.is_logged_in():
            return True
        if on_auth_error:
            on_auth_error()
            return cl.is_logged_in()
        return False

    # ------------------------------------------------ ۱) جستجو و ذخیره سرنخ‌ها
    for page in range(1, pages + 1):
        if page > 1:
            limiter.wait("page")
        try:
            posts = cl.search(keyword, cities=cities, page=page)
            bump_quota(con, "searches", len(posts))
        except DivarBlockedError as e:
            if _handle_block(cfg, breaker, e) == "fatal":
                break
            limiter.slow_down(cfg.get("backoff_multiplier", 1.5))
            continue  # همین صفحه دوباره (حلقه برای سادگی از continue استفاده می‌کند)
        except Exception as e:
            print(f"[!] خطا در صفحه {page}: {e}")
            break
        if not posts:
            print(f"[*] صفحه {page}: نتیجه‌ای نبود — پایان نتایج")
            break
        new_in_page = 0
        for p in posts:
            counters["posts_seen"] += 1
            if upsert_lead(con, p, keyword,
                           ",".join(_pretty(c) for c in cities) if cities else "iran"):
                counters["new_posts"] += 1
                new_in_page += 1
        con.commit()
        print(f"[*] صفحه {page}: {len(posts)} آگهی ({new_in_page} جدید)")
        if new_in_page == 0 and page >= 2:
            break  # بقیه صفحات تکراری‌اند

    if no_phone:
        log_run(con, keyword=keyword, city=str(cities), pages=pages, **counters,
                started_at=started)
        con.commit()
        con.close()
        return counters

    # ------------------------------------------- ۲) شماره‌گیری سرنخ‌های جدید
    quota_left = cfg.get("phone_daily_limit", 80) - quota_today(con)["phones"]
    if quota_left <= 0:
        notify(cfg, f"سهمیه روزانه شماره ({cfg.get('phone_daily_limit', 80)}) "
                    "پر شده — فردا ادامه می‌دهیم. (سهمیه در config.json)")
    else:
        if not ensure_login():
            print("[!] بدون لاگین نمی‌توان شماره گرفت؛ فقط آگهی‌ها ذخیره شدند.")
        targets = pending_phone(con, keyword)
        if max_phones > 0:
            targets = targets[:min(max_phones, quota_left)]
        else:
            targets = targets[:quota_left]
        if targets:
            print(f"[*] دریافت شماره برای {len(targets)} سرنخ "
                  f"(سهمیه باقی‌مانده امروز: {quota_left})")
        for i, row in enumerate(targets, 1):
            if breaker.is_fatal():
                break
            try:
                res = cl.get_phone(row["token"])
                bump_quota(con, "phones")
                breaker.reset()  # یک موفقیت یعنی وضعیت عادی
            except DivarAuthError as e:
                print(f"[!] {e}")
                if ensure_login():
                    try:
                        res = cl.get_phone(row["token"])
                        bump_quota(con, "phones")
                    except Exception as e2:
                        res = {"status": "error", "message": str(e2)}
                else:
                    break
            except DivarBlockedError as e:
                if _handle_block(cfg, breaker, e) == "fatal":
                    break
                limiter.slow_down(cfg.get("backoff_multiplier", 1.5))
                continue  # این سرنخ بعداً (صف pending) دوباره امتحان می‌شود
            except Exception as e:
                res = {"status": "error", "message": str(e)}
            set_phone(con, row["token"], res)
            con.commit()
            st = res.get("status")
            if st == "found":
                counters["phones_found"] += 1
                print(f"  [{i}/{len(targets)}] ✓ {row['title'][:35]} → {res['phone']}")
            elif st == "hidden":
                counters["phones_hidden"] += 1
                print(f"  [{i}/{len(targets)}] − {row['title'][:35]} → فقط چت")
            elif st == "removed":
                print(f"  [{i}/{len(targets)}] × {row['title'][:35]} → حذف شده")
            else:
                counters["errors"] += 1
                print(f"  [{i}/{len(targets)}] ✗ {row['title'][:35]} → "
                      f"{res.get('message', '')[:60]}")

    log_run(con, keyword=keyword, city=str(cities), pages=pages, **counters,
            started_at=started)
    con.commit()
    con.close()
    return counters
