# -*- coding: utf-8 -*-
"""پیام‌سازی نیمه‌خودکار (Human-in-the-Loop) برای سرنخ‌های «فقط چت».

جریان: متن شخصی‌سازی‌شده ساخته می‌شود → چت آگهی در مرورگر باز می‌شود →
اپراتور متن را Paste و ارسال می‌کند → وضعیت سرنخ ثبت می‌شود.
این مسیر بن نمی‌سازد چون ارسال واقعی را انسان انجام می‌دهد.
"""

from __future__ import annotations

import sqlite3
import time
import webbrowser
from typing import Any, Dict, Optional


def build_message(template: str, lead: sqlite3.Row | Dict[str, Any]) -> str:
    """قالب را با اطلاعات همان آگهی پر می‌کند (شخصی‌سازی = ضد اسپم)."""
    return template.format(
        title=(lead["title"] or "").strip() or "آگهی شما",
        subtitle=lead["subtitle"] or "",
        url=lead["url"] or "",
    )


def copy_to_clipboard(text: str) -> bool:
    """کپی در کلیپ‌بورد اگر pyperclip باشد؛ وگرنه False (متن چاپ می‌شود)."""
    try:
        import pyperclip  # اختیاری: pip install pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        return False


def draft_flow(con: sqlite3.Connection, keyword: Optional[str] = None,
               template: str = "", limit: int = 0,
               only_chat_only: bool = False) -> None:
    """حلقه تعاملی آماده‌سازی پیام چت برای سرنخ‌های در انتظار تماس."""
    q = ("SELECT * FROM leads WHERE lead_status='new' "
         "AND phone_status IN ('hidden','pending','found','error')")
    args: tuple = ()
    if keyword:
        q += " AND keyword=?"
        args = (keyword,)
    if only_chat_only:
        q += " AND phone_status='hidden'"
    q += " ORDER BY id DESC"
    rows = con.execute(q, args).fetchall()
    if limit > 0:
        rows = rows[:limit]
    if not rows:
        print("سرنخ جدیدی برای پیام چت نیست (همه contacted یا فهرست خالی).")
        return

    print(f"{len(rows)} سرنخ آماده پیام چت است. جریان برای هر سرنخ:\n"
          "  1) متن ساخته و در کلیپ‌بورد کپی می‌شود\n"
          "  2) چت آگهی در مرورگر باز می‌شود\n"
          "  3) شما متن را Paste و ارسال می‌کنید\n"
          "  4) Enter → سرنخ بعدی (s=رد کردن، q=پایان)\n")
    sent = 0
    for row in rows:
        msg = build_message(template, row)
        print("─" * 56)
        print(f"✉️  {row['title']}  ({row['url']})")
        print(f"    شماره: {row['phone'] or '—'} [{row['phone_status']}]")
        print("    متن پیشنهادی:")
        for line in msg.splitlines():
            print(f"    | {line}")
        copied = copy_to_clipboard(msg)
        webbrowser.open(row["url"])
        print(f"    {'✓ در کلیپ‌بورد کپی شد' if copied else '↑ کپی دستی: متن بالا'}"
              " — چت در مرورگر باز شد")
        ans = input("    ارسال کردید؟ (Enter=ثبت contacted / s=رد / q=پایان): ").strip().lower()
        if ans == "q":
            break
        if ans != "s":
            con.execute("UPDATE leads SET lead_status='contacted', notes=? "
                        "WHERE token=?", (f"chat draft sent {time.strftime('%Y-%m-%d %H:%M')}",
                                          row["token"]))
            con.commit()
            sent += 1
    print(f"\n[i] {sent} سرنخ contacted شد. ادامه در اجرای بعدی از همین‌جا پیش می‌رود.")
