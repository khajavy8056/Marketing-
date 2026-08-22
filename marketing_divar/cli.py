# -*- coding: utf-8 -*-
"""رابط خط فرمان سیستم جمع‌آوری سرنخ دیوار.

مثال‌ها:
  python -m marketing_divar login
  python -m marketing_divar collect -k "آپارتمان" --city 1 --pages 2
  python -m marketing_divar collect -k "tutoring" --city 1 --city 3 --max-phones 50
  python -m marketing_divar collect -k "test" --no-phone          # فقط ذخیره آگهی‌ها
  python -m marketing_divar stats
  python -m marketing_divar export --csv out.csv --only-phone
  python -m marketing_divar mark TOKEN contacted                  # وضعیت پیگیری
"""

from __future__ import annotations

import argparse
import sys

from .client import DivarAuthError, DivarClient
from .collector import run_collection
from .db import connect, export_csv, set_lead_status, stats


def cmd_login(args: argparse.Namespace) -> None:
    cl = DivarClient()
    if cl.is_logged_in() and not args.force:
        print("از قبل لاگین هستید. برای لاگین مجدد: login --force")
        return
    cl.login_interactive(args.phone or None)


def cmd_collect(args: argparse.Namespace) -> None:
    def relogin() -> None:
        print("[i] نیازمند لاگین مجدد…")
        DivarClient().login_interactive()

    counters = run_collection(
        keyword=args.keyword,
        cities=args.city or None,
        pages=args.pages,
        delay=args.delay,
        max_phones=args.max_phones,
        no_phone=args.no_phone,
        db_path=args.db,
        on_auth_error=relogin,
    )
    print("=" * 56)
    print("خلاصه دور جمع‌آوری:")
    print(f"  آگهی دیده‌شده:  {counters['posts_seen']}")
    print(f"  سرنخ جدید:      {counters['new_posts']}")
    print(f"  شماره گرفته‌شده: {counters['phones_found']}")
    print(f"  فقط چت (مخفی):  {counters['phones_hidden']}")
    print(f"  خطا:            {counters['errors']}")
    print("=" * 56)


def cmd_stats(_: argparse.Namespace) -> None:
    con = connect()
    rows = stats(con)
    if not rows:
        print("هنوز داده‌ای نیست. اول collect اجرا کنید.")
        return
    hdr = f"{'کلمه‌کلیدی':<24}{'کل':>6}{' شماره‌دار':>11}{' مخفی':>8}{' در صف':>8}{' خطا':>6}{' تماس‌گرفته':>12}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{(r['keyword'] or '')[:23]:<24}{r['total']:>6}"
              f"{r['with_phone'] or 0:>11}{r['hidden_phone'] or 0:>8}"
              f"{r['pending'] or 0:>8}{r['errors'] or 0:>6}{r['contacted'] or 0:>12}")
    con.close()


def cmd_export(args: argparse.Namespace) -> None:
    con = connect()
    n = export_csv(con, args.csv, only_with_phone=args.only_phone)
    con.close()
    print(f"✓ {n} ردیف در «{args.csv}» ذخیره شد "
          f"({'فقط شماره‌دارها' if args.only_phone else 'همه سرنخ‌ها'})")


def cmd_mark(args: argparse.Namespace) -> None:
    con = connect()
    set_lead_status(con, args.token, args.status)
    con.commit()
    con.close()
    print(f"✓ وضعیت سرنخ {args.token} → {args.status}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="marketing_divar",
                                 description="سیستم جمع‌آوری سرنخ و شماره تماس از دیوار")
    ap.add_argument("--db", default="data/divar_leads.db", help="مسیر دیتابیس")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("login", help="لاگین با شماره موبایل + کد پیامکی")
    p.add_argument("--phone", help="شماره موبایل (09xxxxxxxxx)")
    p.add_argument("--force", action="store_true", help="نادیده گرفتن سشن فعلی")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("collect", help="جمع‌آوری آگهی‌ها و شماره‌ها برای یک کلمه‌کلیدی")
    p.add_argument("-k", "--keyword", required=True, help="کلمه‌کلیدی جستجو")
    p.add_argument("--city", action="append", type=int,
                   help="کد شهر (قابل تکرار): 1=تهران 2=کرج 3=مشهد 4=اصفهان …")
    p.add_argument("--pages", type=int, default=1, help="تعداد صفحات جستجو")
    p.add_argument("--delay", type=float, default=3.0,
                   help="مکث بین درخواست‌های شماره (ثانیه)")
    p.add_argument("--max-phones", type=int, default=0,
                   help="حداکثر تعداد شماره در این دور (0=بدون محدودیت)")
    p.add_argument("--no-phone", action="store_true",
                   help="فقط آگهی‌ها را ذخیره کن، شماره نگیر")
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("stats", help="آمار دیتابیس سرنخ‌ها")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("export", help="خروجی CSV (سازگار با اکسل)")
    p.add_argument("--csv", required=True, help="مسیر فایل خروجی")
    p.add_argument("--only-phone", action="store_true", help="فقط ردیف‌های شماره‌دار")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("mark", help="تغییر وضعیت پیگیری یک سرنخ")
    p.add_argument("token", help="توکن آگهی")
    p.add_argument("status",
                   choices=["new", "contacted", "replied", "converted", "ignored"])
    p.set_defaults(func=cmd_mark)
    return ap


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except DivarAuthError as e:
        sys.exit(f"[✗] {e} — فرمان «login» را اجرا کنید")
    except KeyboardInterrupt:
        sys.exit("\n[i] متوقف شد؛ داده‌های تا این لحظه ذخیره شده‌اند")
