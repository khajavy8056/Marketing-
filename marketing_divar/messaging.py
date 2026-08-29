# -*- coding: utf-8 -*-
"""پیام‌سازی با متغیر — چت خودکار و نیمه‌خودکار.

متغیرها متن را برای هر آگهی عوض می‌کنند تا الگوی اسپم ساخته نشود.
"""

from __future__ import annotations

import random
import sqlite3
import time
import webbrowser
from typing import Any, Dict, Optional

_GREETINGS = (
    "سلام، وقت بخیر 🌹",
    "سلام و درود 🙏",
    "درود، روز بخیر ☀️",
    "سلام، وقتتون بخیر 😊",
    "سلام، امیدوارم حالتون خوب باشه 🌷",
)
_CLOSINGS = (
    "ممنون از وقتی که می‌گذارید 🙏",
    "سپاس از توجه شما 🌹",
    "با تشکر، منتظر پاسخ شما هستم 😊",
    "ممنونم و موفق باشید 🙏",
    "پیشاپیش از پاسخ شما سپاسگزارم 🌷",
)


def _field(lead: Any, key: str, default: str = "") -> str:
    try:
        v = lead[key]
    except (KeyError, IndexError, TypeError):
        v = None
    if v is None:
        if isinstance(lead, dict):
            v = lead.get(key)
        else:
            v = None
    if v is None:
        return default
    return str(v).strip()


def _format_price(value: Any) -> str:
    try:
        n = int(value or 0)
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        return ""
    if n >= 1_000_000:
        return f"{n / 1_000_000:g} میلیون تومان"
    return f"{n:,} تومان"


def build_message(template: str, lead: sqlite3.Row | Dict[str, Any]) -> str:
    """قالب را با اطلاعات همان آگهی پر می‌کند (شخصی‌سازی = ضد اسپم).

    {title} {subtitle} {url} {city} {keyword} {price} {published_at}
    {greeting} {closing} {platform}
    """
    data = {
        "title": _field(lead, "title", "آگهی شما"),
        "subtitle": _field(lead, "subtitle"),
        "url": _field(lead, "url"),
        "city": _field(lead, "city"),
        "keyword": _field(lead, "keyword"),
        "price": _format_price(_field(lead, "price")),
        "published_at": _field(lead, "published_at"),
        "platform": _field(lead, "platform", "divar"),
        "greeting": random.choice(_GREETINGS),
        "closing": random.choice(_CLOSINGS),
    }
    class _Safe(dict):
        def __missing__(self, key):
            return ""
    try:
        return template.format_map(_Safe(data))
    except (IndexError, ValueError):
        return template


def copy_to_clipboard(text: str) -> bool:
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        return False


def draft_flow(con: sqlite3.Connection, keyword: Optional[str] = None,
               template: str = "", limit: int = 0,
               only_chat_only: bool = False) -> None:
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
