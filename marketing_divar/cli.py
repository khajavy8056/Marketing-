# -*- coding: utf-8 -*-
"""رابط خط فرمان سیستم جمع‌آوری سرنخ دیوار.

مثال‌ها:
  python -m marketing_divar login
  python -m marketing_divar collect -k "آپارتمان" --city 1 --pages 2
  python -m marketing_divar collect -k "test" --no-phone            # فقط آگهی‌ها
  python -m marketing_divar draft -k "آپارتمان"                     # پیام چت نیمه‌خودکار
  python -m marketing_divar watch -k "املاک" --city 1 --every 600   # مانیتور دوره‌ای
  python -m marketing_divar stats | export | mark | quota
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from .client import DivarAuthError, DivarBlockedError, DivarClient
from .collector import run_collection
from .db import connect, export_csv, quota_today, set_lead_status, stats
from .messaging import draft_flow
from .paths import apply_runtime_paths


def cmd_login(args: argparse.Namespace) -> None:
    cl = DivarClient()
    if cl.is_logged_in() and not args.force:
        print("از قبل لاگین هستید. برای لاگین مجدد: login --force")
        return
    cl.login_interactive(args.phone or None)


def cmd_collect(args: argparse.Namespace, cfg=None) -> None:
    from .config import load_config
    cfg = cfg or load_config()

    def relogin() -> None:
        print("[i] نیازمند لاگین مجدد…")
        DivarClient().login_interactive()

    counters = run_collection(
        keyword=args.keyword, cities=args.city or None, pages=args.pages,
        max_phones=args.max_phones, no_phone=args.no_phone,
        db_path=args.db, cfg=cfg, on_auth_error=relogin)
    print("=" * 56)
    print("خلاصه دور جمع‌آوری:")
    print(f"  آگهی دیده‌شده:   {counters['posts_seen']}")
    print(f"  سرنخ جدید:       {counters['new_posts']}")
    print(f"  شماره گرفته‌شده: {counters['phones_found']}")
    print(f"  فقط چت (مخفی):   {counters['phones_hidden']}")
    print(f"  خطا:             {counters['errors']}")


def cmd_watch(args: argparse.Namespace) -> None:
    """مانیتور دوره‌ای: هر N ثانیه فقط جستجو و ذخیره سرنخ جدید (بدون شماره، بدون ریسک)."""
    from .config import load_config
    cfg = load_config()
    print(f"[i] مانیتور «{args.keyword}» هر {args.every} ثانیه "
          "(Ctrl+C برای توقف؛ سرنگ‌ها در دیتابیس جمع می‌شوند)")
    rnd = 1
    try:
        while True:
            print(f"\n===== دور {rnd} — {time.strftime('%H:%M:%S')} =====")
            run_collection(keyword=args.keyword, cities=args.city or None,
                           pages=args.pages, no_phone=True, db_path=args.db, cfg=cfg)
            rnd += 1
            time.sleep(args.every)
    except KeyboardInterrupt:
        print("\n[i] مانیتور متوقف شد.")


def cmd_stats(_: argparse.Namespace) -> None:
    con = connect()
    rows = stats(con)
    q = quota_today(con)
    if not rows:
        print("هنوز داده‌ای نیست. اول collect اجرا کنید.")
    else:
        hdr = (f"{'کلمه‌کلیدی':<24}{'کل':>6}{' شماره‌دار':>11}{' مخفی':>8}"
               f"{' در صف':>8}{' خطا':>6}{' تماس‌گرفته':>12}")
        print(hdr)
        print("-" * len(hdr))
        for r in rows:
            print(f"{(r['keyword'] or '')[:23]:<24}{r['total']:>6}"
                  f"{r['with_phone'] or 0:>11}{r['hidden_phone'] or 0:>8}"
                  f"{r['pending'] or 0:>8}{r['errors'] or 0:>6}{r['contacted'] or 0:>12}")
    print(f"\n📊 سهمیه امروز: شماره {q['phones']} / محدود دیتابیس؛ "
          f"جستجو {q['searches']} درخواست")
    con.close()


def cmd_quota(_: argparse.Namespace) -> None:
    con = connect()
    q = quota_today(con)
    print(f"امروز ({time.strftime('%Y-%m-%d')}): "
          f"{q['phones']} شماره‌گیری، {q['searches']} آگهی جستجو شده")
    con.close()


def cmd_export(args: argparse.Namespace) -> None:
    con = connect()
    n = export_csv(con, args.csv, only_with_phone=args.only_phone)
    con.close()
    print(f"✓ {n} ردیف در «{args.csv}» ذخیره شد")


def cmd_mark(args: argparse.Namespace) -> None:
    con = connect()
    set_lead_status(con, args.token, args.status)
    con.commit()
    con.close()
    print(f"✓ وضعیت سرنخ {args.token} → {args.status}")


def cmd_draft(args: argparse.Namespace) -> None:
    from .config import load_config
    cfg = load_config()
    con = connect()
    draft_flow(con, keyword=args.keyword, template=cfg.get("chat_template", "{title}"),
               limit=args.limit, only_chat_only=args.chat_only)
    con.close()


def cmd_accounts(args: argparse.Namespace) -> None:
    from .config import load_config
    cfg = load_config()
    from .accounts import AccountManager
    mgr = AccountManager(cfg)
    if args.action == "login":
        mgr.login_account(args.name)
    elif args.action == "list":
        rows = mgr.snapshot(args.db)
        if not rows:
            print("هیچ اکانتی ثبت نشده. اضافه کردن: accounts login <name>")
        for a in rows:
            mark = {"active": "✅", "captcha": "🧩", "cooldown": "⏳",
                    "relogin": "🔑", "disabled": "⛔"}.get(a["status"], "?")
            print(f" {mark} {a['name']:<12} وضعیت={a['status']:<9} "
                  f"امروز={a['phones_today']} شماره سشن={'دارد' if a['has_token'] else 'ندارد'}")
    elif args.action == "release":
        mgr.release(args.name)
        print(f"✓ اکانت {args.name} آزاد شد")
    elif args.action == "disable":
        mgr.set_status(args.name, "disabled")
        print(f"⛔ اکانت {args.name} غیرفعال شد")


def cmd_hunter_analyze(args: argparse.Namespace) -> None:
    from .db import connect
    from .hunter_analyzer import evaluate_professional, collect_samples_detailed, default_profile
    from .hunter_profile import default_profile as dp
    con = connect()
    try:
        # اگر token داده شده
        if args.token:
            row = con.execute("SELECT * FROM leads WHERE token=?", (args.token,)).fetchone()
            if not row:
                print(f"توکن {args.token} پیدا نشد")
                return
            d = dict(row)
            keyword = d.get("keyword") or ""
            city = d.get("city") or ""
            price = int(d.get("price") or 0)
            samples = collect_samples_detailed(con, keyword, city, limit=80)
            profile = dp(d.get("category") or "", keyword)
            # اگر تنظیمات سفارشی در DB هست
            try:
                import json
                adv = d.get("hunter_adv") or con.execute("SELECT hunter_adv FROM keywords WHERE id=?", (d.get("keyword_id") or 0,)).fetchone()
                # ساده
            except Exception:
                pass
            res = evaluate_professional(price, samples, profile, extra=d, text=f"{d.get('title','')} {d.get('description','')}", enable_web_price=args.web)
            print(f"عنوان: {d.get('title')}")
            print(f"قیمت: {price:,} تومان")
            print(f"بازار سالم: {res.get('healthy_median',0):,} (خام {res.get('raw_median',0):,})")
            print(f"منصفانه: {res.get('fair',0):,}  تخفیف: {res.get('discount_pct')}%  سطح: {res.get('level')}")
            print(f"افت: {res.get('adj_pct')}% (پرچم {res.get('adj_flags_pct')}% + کارکرد {res.get('adj_mileage_pct')}% + سال {res.get('adj_year_pct')}%)")
            print(f"پرچم‌ها: {res.get('flags')}")
            print(f"اطمینان: {res.get('confidence')}  نمونه: {res.get('sample_count')}  p10={res.get('market',{}).get('p10',0):,}")
            if res.get("pending"):
                print(f"در انتظار: {res.get('missing')} → سوال: {res.get('questions')}")
            if res.get("web_price"):
                print(f"قیمت وب: {res.get('web_price'):,} منبع: {res.get('web_price_source')}")
        else:
            # تحلیل کل hunter
            rows = con.execute("SELECT token, title, price, keyword, city FROM leads WHERE hunter_level IN ('good','great','pending','suspicious') ORDER BY id DESC LIMIT ?", (args.limit,)).fetchall()
            for r in rows:
                d = dict(r)
                samples = collect_samples_detailed(con, d.get("keyword") or "", d.get("city") or "", limit=50)
                profile = dp("", d.get("keyword") or "")
                res = evaluate_professional(int(d.get("price") or 0), samples, profile, extra=d, text=d.get("title") or "", enable_web_price=args.web)
                print(f"{d['token'][:8]} | {d['title'][:40]:<40} | {d['price']:>12,} | {res.get('level'):<10} | {res.get('discount_pct')}% | conf {res.get('confidence')}")
    finally:
        con.close()


def cmd_hunter_negotiate(args: argparse.Namespace) -> None:
    from .db import connect
    from .hunter_negotiator import negotiate_next
    con = connect()
    try:
        row = con.execute("SELECT * FROM leads WHERE token=?", (args.token,)).fetchone()
        if not row:
            print(f"توکن {args.token} پیدا نشد")
            return
        d = dict(row)
        res = negotiate_next(d, con)
        print(f"مذاکره: {res}")
        con.commit()
    finally:
        con.close()


def cmd_hunter_vip(args: argparse.Namespace) -> None:
    from .db import connect
    con = connect()
    try:
        q = "SELECT token, title, price, hunter_level, hunter_discount_pct, hunter_fair_price, hunter_market_median, hunter_confidence, negotiated_price, negotiation_status FROM leads WHERE hunter_level IN ('good','great') ORDER BY hunter_discount_pct DESC LIMIT ?"
        rows = con.execute(q, (args.limit,)).fetchall()
        print(f"{'TOKEN':<10} {'TITLE':<40} {'PRICE':>12} {'LEVEL':<8} {'DISC%':>6} {'FAIR':>12} {'CONF':>5} {'NEG':>12} {'STATUS'}")
        for r in rows:
            d = dict(r)
            print(f"{d['token'][:8]:<10} {d['title'][:38]:<40} {d['price'] or 0:>12,} {d['hunter_level'] or '':<8} {d['hunter_discount_pct'] or 0:>6} {d['hunter_fair_price'] or 0:>12,} {d['hunter_confidence'] or 0:>5} {d['negotiated_price'] or 0:>12,} {d['negotiation_status'] or ''}")
    finally:
        con.close()


def cmd_monitor(args: argparse.Namespace) -> None:
    from .config import load_config
    cfg = load_config()
    from .monitor import Monitor
    keywords = []
    for k in args.keyword:
        keywords.append({"keyword": k, "cities": args.city, "pages": args.pages})
    mon = Monitor(cfg, keywords, db_path=args.db,
                  interactive=not args.non_interactive)
    try:
        mon.run()
    finally:
        mon.stop()


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="marketing_divar",
        description="سیستم جمع‌آوری سرنخ و شماره تماس از دیوار (نسخه ضد بلاک)")
    ap.add_argument("--db", default=os.environ.get("DIVAR_DB_PATH", "data/divar_leads.db"),
                   help="مسیر دیتابیس")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("login", help="لاگین با شماره موبایل + کد پیامکی")
    p.add_argument("--phone", help="شماره موبایل (09xxxxxxxxx)")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("collect", help="جمع‌آوری آگهی و شماره برای یک کلمه‌کلیدی")
    p.add_argument("-k", "--keyword", required=True)
    p.add_argument("--city", action="append", type=int,
                   help="کد شهر (تکرارپذیر): 1=تهران 2=کرج 3=مشهد 4=اصفهان")
    p.add_argument("--pages", type=int, default=1)
    p.add_argument("--max-phones", type=int, default=0, help="0=تا سقف سهمیه")
    p.add_argument("--no-phone", action="store_true",
                   help="فقط آگهی‌ها را ذخیره کن (بدون ریسک)")
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("watch", help="مانیتور دوره‌ای کلمه‌کلیدی (فقط جستجو)")
    p.add_argument("-k", "--keyword", required=True)
    p.add_argument("--city", action="append", type=int)
    p.add_argument("--pages", type=int, default=1)
    p.add_argument("--every", type=int, default=600, help="فاصله دورها (ثانیه)")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("draft", help="پیام چت نیمه‌خودکار برای سرنخ‌ها")
    p.add_argument("-k", "--keyword")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--chat-only", action="store_true",
                   help="فقط آگهی‌های بدون شماره (فقط چت)")
    p.set_defaults(func=cmd_draft)

    p = sub.add_parser("accounts", help="مدیریت اکانت‌های چندگانه")
    p.add_argument("action", choices=["login", "list", "release", "disable"])
    p.add_argument("name", nargs="?", help="نام اکانت (حروف کوچک)")
    p.set_defaults(func=cmd_accounts)

    p = sub.add_parser("monitor", help="مانیتور لحظه‌ای: آگهی جدید → شماره (چند اکانت)")
    p.add_argument("-k", "--keyword", action="append", required=True,
                   help="کلمه‌کلیدی (تکرارپذیر)")
    p.add_argument("--city", action="append", type=int)
    p.add_argument("--pages", type=int, default=1)
    p.add_argument("--non-interactive", action="store_true",
                   help="بدون شنیدن فرمان‌های ترمینال (برای سرور)")
    p.set_defaults(func=cmd_monitor)

    p = sub.add_parser("stats", help="آمار دیتابیس و سهمیه امروز")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("quota", help="سهمیه مصرفی امروز")
    p.set_defaults(func=cmd_quota)

    p = sub.add_parser("export", help="خروجی CSV سازگار با اکسل")
    p.add_argument("--csv", required=True)
    p.add_argument("--only-phone", action="store_true")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("mark", help="تغییر وضعیت پیگیری سرنخ")
    p.add_argument("token")
    p.add_argument("status", choices=["new", "contacted", "replied",
                                      "converted", "ignored", "removed"])
    p.set_defaults(func=cmd_mark)

    p = sub.add_parser("hunter", help="تحلیل حرفه‌ای شکارچی (میانه سالم + تخفیف واقعی)")
    p.add_argument("--token", help="توکن یک آگهی خاص")
    p.add_argument("--limit", type=int, default=20, help="تعداد برای لیست کلی")
    p.add_argument("--web", action="store_true", help="قیمت وب را هم امتحان کن (اختیاری)")
    p.set_defaults(func=cmd_hunter_analyze)

    p = sub.add_parser("hunter-negotiate", help="شروع/ادامه مذاکره شکارچی برای یک توکن")
    p.add_argument("token", help="توکن آگهی")
    p.set_defaults(func=cmd_hunter_negotiate)

    p = sub.add_parser("hunter-vip", help="لیست VIP حرفه‌ای (خوب/عالی)")
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(func=cmd_hunter_vip)
    return ap


def main(argv=None) -> None:
    apply_runtime_paths()
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except DivarAuthError as e:
        sys.exit(f"[✗] {e} — فرمان «login» را اجرا کنید")
    except DivarBlockedError as e:
        sys.exit(f"[✗] دیوار محدود کرد: {e}\n"
                 "    ۳۰ دقیقه صبر کنید و دوباره اجرا کنید؛ اگر تکرار شد "
                 "سهمیه/تاخیرها را در config.json بیشتر کنید.")
    except KeyboardInterrupt:
        sys.exit("\n[i] متوقف شد؛ همه داده‌های تا این لحظه ذخیره شده‌اند")
