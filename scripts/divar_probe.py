#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
divar_probe.py — اسکریپت راستی‌آزمایی امکان‌سنجی سیستم جستجوی کلمه‌کلیدی دیوار
================================================================================
این اسکریپت باید روی سیستمی با IP ایران اجرا شود (سرورهای دیوار معمولاً
به IPهای خارج از ایران پاسخ نمی‌دهند).

چه چیزی را تست می‌کند؟
  1) جستجوی کلمه‌کلیدی با API غیررسمی وب‌سایت دیوار (بدون لاگین)
  2) شمارش نتایج (کل و در هر صفحه)
  3) استخراج توکن‌های آگهی (برای باز کردن صفحه آگهی/چت)
  4) دریافت جزئیات یک آگهی نمونه
  5) اندپوینت اطلاعات تماس (انتظار: احتمالاً بدون لاگین جواب نمی‌دهد)
  6) [اختیاری] API رسمی «کنار دیوار» در صورت ارائه X-API-Key

نصب پیش‌نیاز:  pip install requests

مثال‌ها:
  python divar_probe.py --keyword "آپارتمان" --city tehran
  python divar_probe.py --keyword "گوشی آیفون" --city tehran --category light
  python divar_probe.py --keyword "تدریس" --city mashhad --pages 3 --out results.json
  KAPI_KEY=xxxxxxxx python divar_probe.py --keyword "آپارتمان" --city tehran --official

خروجی: گزارش متنی + فایل JSON شامل آگهی‌های یافت‌شده (توکن، عنوان، لینک چت).
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:  # برای --help بدون نصب هم کار کند؛ در اجرای واقعی چک می‌شود
    requests = None  # type: ignore


def need_requests() -> None:
    if requests is None:
        sys.exit("پکیج requests نصب نیست. اجرا کنید:  pip install requests")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BASE = "https://api.divar.ir"
OPEN_BASE = "https://open-api.divar.ir"
POLITE_DELAY = 1.5  # ثانیه بین درخواست‌ها — مؤدبانه بمانیم تا IP بلاک نشود


def log(msg: str) -> None:
    print(f"[*] {msg}")


def ok(msg: str) -> None:
    print(f"[✓] {msg}")


def warn(msg: str) -> None:
    print(f"[!] {msg}")


def fail(msg: str) -> None:
    print(f"[✗] {msg}")


# ---------------------------------------------------------------- غیررسمی --
def web_search_page(city: str, keyword: str, category: Optional[str],
                    page_from: Optional[int] = None) -> Dict[str, Any]:
    """یک صفحه از نتایج جستجو را می‌گیرد.

    الگوی URL که سایت divar.ir خودش استفاده می‌کند:
      GET /v8/web-search/{city}/{category}?q={keyword}
      GET /v8/web-search/{city}?q={keyword}        (بدون دسته‌بندی)
    صفحه‌بندی با پارامتر page (شماره صفحه) انجام می‌شود.
    """
    path = f"/v8/web-search/{city}"
    if category:
        path += f"/{category}"
    params: Dict[str, Any] = {"q": keyword}
    if page_from is not None:
        params["page"] = page_from
    r = requests.get(BASE + path, params=params,
                     headers={"User-Agent": UA, "Accept": "application/json"},
                     timeout=20)
    r.raise_for_status()
    return r.json()


def extract_posts(page_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """توکن و عنوان آگهی‌ها را از ساختار ویجتی پاسخ بیرون می‌کشد (مقاوم به تغییر)."""
    posts: List[Dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("widget_type") in ("POST_ROW", "POST_ROW_MARKETPLACE"):
                data = node.get("data") or {}
                token = data.get("token")
                if token:
                    posts.append({
                        "token": token,
                        "title": data.get("title"),
                        "url": f"https://divar.ir/v/{token}",
                        "chat_url": f"https://divar.ir/v/{token}#chat",
                    })
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(page_json)
    # حذف تکراری‌ها بر اساس توکن
    seen, uniq = set(), []
    for p in posts:
        if p["token"] not in seen:
            seen.add(p["token"])
            uniq.append(p)
    return uniq


def find_total_hint(page_json: Dict[str, Any]) -> Optional[str]:
    """سعی می‌کند عدد تقریبی «کل آگهی‌ها» را از فیلدهای مختلف پاسخ پیدا کند."""
    candidates = []
    seo = page_json.get("search_data") or {}
    if isinstance(seo, dict):
        candidates.append(seo.get("total"))
        candidates.append((page_json.get("header") or {}).get("total"))
    for k in ("total", "total_count", "count"):
        candidates.append(page_json.get(k))
    for c in candidates:
        if isinstance(c, (int, str)) and c not in (0, "0"):
            return str(c)
    return None


def probe_unofficial(args: argparse.Namespace) -> List[Dict[str, Any]]:
    print("=" * 64)
    print("۱) تست مسیر غیررسمی (api.divar.ir) — بدون احراز هویت")
    print("=" * 64)
    all_posts: List[Dict[str, Any]] = []
    total_hint: Optional[str] = None

    try:
        first = web_search_page(args.city, args.keyword, args.category)
        ok(f"جستجو با کلمه «{args.keyword}» در «{args.city}» جواب داد (HTTP 200)")
        page_posts = extract_posts(first)
        total_hint = find_total_hint(first)
        all_posts.extend(page_posts)
        ok(f"تعداد آگهی در صفحه اول: {len(page_posts)}")
        if total_hint:
            ok(f"عدد کل اعلام‌شده توسط سرور: ~{total_hint}")
        else:
            warn("فیلد «کل نتایج» در پاسخ نبود — با صفحه‌بندی کامل شمرده می‌شود")
    except requests.exceptions.HTTPError as e:
        fail(f"خطای HTTP در جستجو: {e}")
        warn("ممکن است ساختار URL عوض شده باشد یا IP شما محدود باشد")
        return all_posts
    except requests.exceptions.RequestException as e:
        fail(f"اتصال برقرار نشد: {e}")
        warn("اگر IP خارج از ایران است، دیوار احتمالاً پاسخ نمی‌دهد")
        return all_posts

    # صفحات بعدی
    if args.pages > 1:
        log(f"صفحه‌بندی تا {args.pages} صفحه…")
        for p in range(2, args.pages + 1):
            time.sleep(POLITE_DELAY)
            try:
                nxt = web_search_page(args.city, args.keyword, args.category, page_from=p)
                pp = extract_posts(nxt)
                if not pp:
                    warn(f"صفحه {p}: نتیجه‌ای نبود — احتمالاً پایان نتایج")
                    break
                all_posts.extend(pp)
                log(f"صفحه {p}: {len(pp)} آگهی")
            except Exception as e:
                warn(f"صفحه {p} ناموفق: {e}")
                break

    # تست جزئیات آگهی نمونه
    if all_posts:
        tok = all_posts[0]["token"]
        log(f"تست دریافت جزئیات آگهی نمونه: {tok}")
        time.sleep(POLITE_DELAY)
        try:
            r = requests.get(f"{BASE}/v8/post/{tok}",
                             headers={"User-Agent": UA}, timeout=20)
            if r.ok:
                ok("دریافت جزئیات آگهی موفق (GET /v8/post/{token})")
            else:
                warn(f"جزئیات آگهی: HTTP {r.status_code} — ممکن است نسخه عوض شده باشد")
        except Exception as e:
            warn(f"جزئیات آگهی ناموفق: {e}")

        log("تست اندپوینت اطلاعات تماس (بدون لاگین)…")
        time.sleep(POLITE_DELAY)
        try:
            r = requests.get(f"{BASE}/v8/post/{tok}/contact",
                             headers={"User-Agent": UA}, timeout=20)
            if r.ok and "phone" in r.text.lower():
                ok("!!! شماره تلفن بدون لاگین هم برمی‌گردد")
            elif r.status_code in (401, 403):
                warn("اطلاعات تماس بدون لاگین بسته است (انتظار می‌رفت)")
            else:
                warn(f"اطلاعات تماس: HTTP {r.status_code} (بدون شماره در پاسخ)")
        except Exception as e:
            warn(f"اطلاعات تماس ناموفق: {e}")

    return all_posts


# ------------------------------------------------------------------ رسمی --
def probe_official(args: argparse.Namespace) -> None:
    print("=" * 64)
    print("۲) تست مسیر رسمی (open-api.divar.ir — کنار دیوار)")
    print("=" * 64)
    key = os.environ.get("KAPI_KEY", "")
    if not key:
        warn("متغیر KAPI_KEY تنظیم نشده — تست رسمی رد شد")
        warn("برای دریافت کلید: در my.divar.ir ثبت‌نام و اپلیکیشن بسازید")
        return
    hdr = {"X-API-Key": key, "Content-Type": "application/json"}

    # ۱) جستجو (توجه: طبق مستندات فیلد متن آزاد ندارد — با فیلتر شهر/دسته)
    body: Dict[str, Any] = {"city": args.city}
    if args.category:
        body["category"] = args.category
    try:
        r = requests.post(f"{OPEN_BASE}/v2/open-platform/finder/post",
                          headers=hdr, json=body, timeout=20)
        if r.ok:
            data = r.json()
            n = len(data.get("posts") or [])
            ok(f"جستجوی رسمی موفق — {n} آگهی در پاسخ")
        else:
            warn(f"جستجوی رسمی: HTTP {r.status_code} → {r.text[:300]}")
    except Exception as e:
        fail(f"جستجوی رسمی ناموفق: {e}")

    # ۲) دریافت آگهی نمونه با توکن (اگر از مسیر غیررسمی توکنی داریم)
    tok = getattr(args, "_sample_token", None)
    if tok:
        try:
            r = requests.get(f"{OPEN_BASE}/v1/open-platform/finder/post/{tok}",
                             headers=hdr, timeout=20)
            if r.ok:
                ok("دریافت رسمی جزئیات آگهی موفق")
                print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:1200])
            else:
                warn(f"دریافت رسمی آگهی: HTTP {r.status_code} — اسکوپ GET_POST لازم است")
        except Exception as e:
            warn(f"دریافت رسمی آگهی ناموفق: {e}")


# ------------------------------------------------------------------- main --
def main() -> None:
    ap = argparse.ArgumentParser(description="راستی‌آزمایی API دیوار")
    ap.add_argument("--keyword", "-k", required=True, help="کلمه‌کلیدی جستجو")
    ap.add_argument("--city", "-c", default="tehran",
                    help="شناسه شهر (tehran, mashhad, isfahan, ...)")
    ap.add_argument("--category", default=None,
                    help="شناسه دسته‌بندی (اختیاری؛ مثل light, apartment-rent)")
    ap.add_argument("--pages", "-p", type=int, default=2,
                    help="تعداد صفحات جستجو (پیش‌فرض ۲)")
    ap.add_argument("--out", "-o", default=None, help="مسیر فایل خروجی JSON")
    ap.add_argument("--official", action="store_true",
                    help="تست API رسمی کنار هم انجام شود (نیاز به KAPI_KEY)")
    args = ap.parse_args()
    need_requests()

    posts = probe_unofficial(args)
    if posts:
        args._sample_token = posts[0]["token"]
        print("-" * 64)
        print("نمونه نتایج:")
        for p in posts[:10]:
            print(f"   • {p['title'] or '(بدون عنوان)'}  →  {p['url']}")

    if args.official:
        probe_official(args)

    if args.out and posts:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"keyword": args.keyword, "city": args.city,
                       "count": len(posts), "posts": posts},
                      f, ensure_ascii=False, indent=2)
        ok(f"{len(posts)} آگهی در «{args.out}» ذخیره شد")

    print("=" * 64)
    print("جمع‌بندی تست:")
    print(f"   کل آگهی‌های جمع‌آوری‌شده: {len(posts)}")
    print("   لینک چت هر آگهی: https://divar.ir/v/{token}")
    print("=" * 64)


if __name__ == "__main__":
    main()
