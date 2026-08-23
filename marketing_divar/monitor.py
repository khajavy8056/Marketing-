# -*- coding: utf-8 -*-
"""مانیتور لحظه‌ای: به محض آگهی جدید با کلمه‌کلیدی → گرفتن شماره با چرخش
بین چند اکانت، بدون توقف هنگام کپچای یک اکانت (بقیه ادامه می‌دهند).

جریان‌ها:
  🔎 Watcher (بدون لاگین، کم‌ریسک): هر watch_interval ثانیه کلمه‌کلیدی‌ها را
     جستجو می‌کند؛ آگهی جدید → صف pending.
  📞 Worker (با اکانت‌ها): صف pending را با چرخش اکانت‌ها خالی می‌کند؛
     شماره پیدا شد → ذخیره؛ فقط چت → لیست چت (فرمان draft).
  🧑‍✈️ اپراتور: هنگام کپچا/لاگین، ترمینال یا تلگرام پیام می‌گیرد؛
     در مرورگر حل می‌کند و «release NAME» می‌زند — سیستم تمام نشده،
     بقیه اکانت‌ها در همین لحظه کار می‌کنند.

فرمان‌های داخل اجرا (ترمینال): status | release NAME | pause | resume | quit
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from .accounts import AccountManager
from .client import DivarAuthError, DivarBlockedError, DivarClient
from .db import (bump_quota, chat_queue, connect, pending_phone, quota_today,
                 set_phone, upsert_lead)
from .notifier import notify
from .rate import RateLimiter


class CommandListener(threading.Thread):
    """شنیدن فرمان‌های اپراتور در پس‌زمینه (بدون قفل‌کردن حلقه اصلی)."""

    def __init__(self, monitor: "Monitor"):
        super().__init__(daemon=True)
        self.monitor = monitor

    def run(self) -> None:
        m = self.monitor
        print("  فرمان‌ها: status | release <اکانت> | pause | resume | quit")
        while not m.stop_event.is_set():
            try:
                line = input().strip()
            except EOFError:
                return
            if not line:
                continue
            parts = line.split()
            cmd = parts[0].lower()
            if cmd == "status":
                m.print_status()
            elif cmd == "release" and len(parts) > 1:
                m.mgr.release(parts[1])
                print(f"  ✓ اکانت {parts[1]} آزاد شد")
            elif cmd == "pause":
                m.paused = True
                print("  ⏸ متوقف (resume برای ادامه)")
            elif cmd == "resume":
                m.paused = False
            elif cmd == "quit":
                m.stop_event.set()
                print("  در حال خروج امن…")


class Monitor:
    def __init__(self, cfg: Dict[str, Any], keywords: List[Dict[str, Any]],
                 db_path: str = "data/divar_leads.db",
                 accounts_dir: str = "data/accounts",
                 interactive: bool = True,
                 base_url: Optional[str] = None,
                 on_event=None):
        self.cfg = cfg
        self.keywords = keywords  # [{"keyword": "...", "cities": [1], "pages": 1}]
        self.db_path = db_path
        self.base_url = base_url
        self.interactive = interactive
        self.mgr = AccountManager(cfg, accounts_dir)
        self.stop_event = threading.Event()
        self.paused = False
        self.tick = 0
        # محدودکننده سراسری: هر چه اکانت زیاد، پهنای باند IP ثابت می‌ماند
        self.limiter = RateLimiter(
            phone_delay=cfg.get("phone_delay_sec", 10),
            search_delay=cfg.get("search_delay_sec", 5),
            page_delay=cfg.get("search_page_delay_sec", 8),
            jitter=cfg.get("jitter_sec", 4))
        self.on_event = on_event  # (level, message) — مثلاً برای رخدادنمای وب
        self._clients: Dict[str, DivarClient] = {}
        self._anon: Optional[DivarClient] = None
        self._notified_all_stuck = False

    def _ev(self, level: str, message: str) -> None:
        """رخداد را به رابط وب (در صورت وجود) می‌فرستد؛ خطای خودش بی‌اثر است."""
        if self.on_event:
            try:
                self.on_event(level, message)
            except Exception:
                pass

    # ------------------------------------------------------------ کلاینت‌ها --
    def client_for(self, name: str) -> DivarClient:
        if name not in self._clients:
            self._clients[name] = DivarClient(
                session_path=str(self.mgr.session_path(name)),
                limiter=self.limiter, base_url=self.base_url)
        else:
            self._clients[name].reload_session()  # شاید لاگین مجدد شده باشد
        return self._clients[name]

    @property
    def anon(self) -> DivarClient:
        if self._anon is None:
            self._anon = DivarClient(session_path="data/accounts/_anon/session.json",
                                     limiter=self.limiter, base_url=self.base_url)
        return self._anon

    # ------------------------------------------------------------ جستجو 🔎 --
    def watch_once(self) -> int:
        """یک دور جستجوی همه کلمه‌کلیدی‌ها؛ تعداد سرنخ جدید را برمی‌گرداند."""
        con = connect(self.db_path)
        new_total = 0
        try:
            for spec in self.keywords:
                kw = spec["keyword"]
                cities = spec.get("cities")
                pages = int(spec.get("pages", 1))
                for page in range(1, pages + 1):
                    try:
                        posts = self.anon.search(kw, cities=cities, page=page)
                        bump_quota(con, "searches", len(posts))
                    except DivarBlockedError as e:
                        notify(self.cfg, f"جستجو هم محدود شد!؟ ({e}) — "
                                         "watch_interval را در config.json بزرگ کنید")
                        self._ev("error", f"جستجو متوقف شد: {e}")
                        return new_total
                    except Exception as e:
                        hint = ""
                        if any(k in type(e).__name__ for k in ("Proxy", "Connect", "Timeout", "SSLError")) \
                                or "proxy" in str(e).lower():
                            hint = " — اتصال برقرار نشد؛ VPN/پروکسی و اینترنت را بررسی کنید"
                        print(f"[!] جستجو «{kw}» صفحه {page}: {e}{hint}")
                        self._ev("error", f"خطای جستجوی «{kw}»: {e}{hint}")
                        break
                    new_here = 0
                    for p in posts:
                        city = ",".join(str(c) for c in cities) if cities else "iran"
                        if upsert_lead(con, p, kw, city):
                            new_total += 1
                            new_here += 1
                    con.commit()
                    if new_here == 0:
                        break  # صفحه بعدی تکراری
            return new_total
        finally:
            con.close()

    # ------------------------------------------------------- شماره‌گیری 📞 --
    def _global_quota_left(self, con) -> int:
        return self.cfg.get("ip_daily_limit", 240) - quota_today(con)["phones"]

    def _fetch_one(self) -> str:
        """یک سرنخ از صف را با یک اکانت موجود پردازش می‌کند.
        خروجی: 'done' | 'empty' (صف خالی) | 'wait' (اکانت/سهمیه نیست) | 'quota_done'
        """
        con = connect(self.db_path)
        try:
            if self._global_quota_left(con) <= 0:
                self._ev("warning", f"سهمیه شماره‌گیری امروز ({self.cfg.get('ip_daily_limit', 240)}) پر شد")
                notify(self.cfg, f"سهمیه کلی امروز ({self.cfg.get('ip_daily_limit', 240)}) "
                                 "پر شد — فردا ادامه می‌دهیم.")
                return "quota_done"
            rows = pending_phone(con, limit=1, newest_first=True)
            if not rows:
                return "empty"
            name = self.mgr.pick(self.db_path)
            if not name:
                if not self._notified_all_stuck:
                    snap = self.mgr.snapshot(self.db_path)
                    stuck = ", ".join(f"{a['name']}({a['status']})"
                                      for a in snap if a["status"] != "active") or "سهمیه پر"
                    self._ev("error", f"هیچ اکانت آماده نیست: {stuck} — "
                                      "اگر کپچاست از بخش اکانت‌ها حل و آزاد کنید")
                    notify(self.cfg, f"هیچ اکانت آماده نیست: {stuck}. "
                                     "اگر کپچاست: در مرورگر حل کنید و بنویسید: release <نام>")
                    self._notified_all_stuck = True
                return "wait"
            self._notified_all_stuck = False
            row = rows[0]
            cl = self.client_for(name)
            try:
                res = cl.get_phone(row["token"])
            except DivarAuthError as e:
                self.mgr.set_status(name, "relogin", note=str(e))
                self._ev("error", f"اکانت {name} نیاز به لاگین مجدد دارد")
                notify(self.cfg, f"اکانت {name} نیاز به لاگین مجدد دارد — "
                                 f"در ترمینال دیگر: accounts login {name}")
                return "wait"
            except DivarBlockedError as e:
                # این اکانت می‌ایستد؛ بقیه در فراخوانی بعدی ادامه می‌دهند ✅
                status = "captcha" if "کپچا" in str(e) or "captcha" in str(e).lower() \
                    else "cooldown"
                self.mgr.set_status(
                    name, status,
                    cooldown_sec=self.cfg.get("cooldown_on_block_min", 30) * 60,
                    note=f"{e} (status={e.status})")
                self._ev("warning" if status == "captcha" else "error",
                         f"اکانت {name} → {status} ({e}). بقیه اکانت‌ها ادامه می‌دهند")
                notify(self.cfg, f"اکانت {name} → {status} ({e}). "
                                 f"بقیه اکانت‌ها ادامه می‌دهند. بعد از حل: release {name}")
                return "wait"
            set_phone(con, row["token"], res)
            bump_quota(con, "phones")
            st0 = res.get("status")
            if st0 == "found":
                self._ev("success", f"📞 شماره پیدا شد: {row['title'][:40]} → {res['phone']}")
            elif st0 == "hidden":
                self._ev("info", f"💬 فقط چت: {row['title'][:40]} (به لیست چت رفت)")
            self.mgr.record_use(self.db_path, name)
            con.commit()
            st = res.get("status")
            if st == "found":
                print(f"  📞 ✓ {name}: {row['title'][:32]} → {res['phone']}")
            elif st == "hidden":
                print(f"  💬 − {name}: {row['title'][:32]} → فقط چت (رفت به لیست چت)")
            elif st == "removed":
                print(f"  × {row['title'][:32]} حذف شده")
            return "done"
        finally:
            con.close()

    def drain(self, max_items: int = 0) -> None:
        """خالی‌کردن صف تا جایی که اکانت/سهمیه هست (بدون بن‌بست)."""
        done = 0
        while not self.stop_event.is_set() and not self.paused:
            r = self._fetch_one()
            if r == "empty" or r == "quota_done":
                return
            if r == "wait":
                # همه اکانت‌ها مشغول‌اند: کمی صبر و دوباره (release را می‌شنود)
                for _ in range(min(self.cfg.get("watch_interval_sec", 300), 60)):
                    if self.stop_event.is_set():
                        return
                    time.sleep(1)
                return  # به دور بعدی ساعت برگرد
            done += 1
            if max_items > 0 and done >= max_items:
                return

    # ------------------------------------------------------------- اجرا --
    def print_status(self) -> None:
        con = connect(self.db_path)
        try:
            q = quota_today(con)
            pend = len(pending_phone(con))
            chat = len(chat_queue(con))
        finally:
            con.close()
        print(f"  ── دور {self.tick} | در صف شماره: {pend} | لیست چت: {chat} | "
              f"امروز: {q['phones']} شماره، {q['searches']} جستجو")
        for a in self.mgr.snapshot(self.db_path):
            mark = {"active": "✅", "captcha": "🧩", "cooldown": "⏳",
                    "relogin": "🔑", "disabled": "⛔"}.get(a["status"], "?")
            print(f"   {mark} {a['name']:<12} {a['status']:<9} "
                  f"امروز {a['phones_today']} شماره {('— ' + a['note'])[:40] if a['note'] else ''}")

    def run(self) -> None:
        interval = self.cfg.get("watch_interval_sec", 300)
        self._ev("success", f"مانیتور شروع شد — {len(self.keywords)} کلمه‌کلیدی، "
                            f"هر {interval} ثانیه یک دور؛ اکانت‌ها: "
                            f"{', '.join(self.mgr.list_accounts()) or 'هیچ!'}")
        print(f"🚀 مانیتور شروع شد — {len(self.keywords)} کلمه‌کلیدی، هر {interval}s؛ "
              f"اکانت‌ها: {', '.join(self.mgr.list_accounts()) or 'هیچ! (accounts login)'}")
        if self.interactive:
            CommandListener(self).start()
        while not self.stop_event.is_set():
            if self.paused:
                time.sleep(1)
                continue
            self.tick += 1
            print(f"\n⏰ دور {self.tick} — {time.strftime('%H:%M:%S')}")
            try:
                new = self.watch_once()
                if new:
                    print(f"  🆕 {new} سرنخ جدید وارد صف شد")
                self.drain()
                self.print_status()
                q = None
                try:
                    _c = connect(self.db_path)
                    try:
                        q = quota_today(_c)
                    finally:
                        _c.close()
                except Exception:
                    pass
                if q:
                    self._ev("success", f"دور {self.tick} تمام شد — امروز: "
                                        f"{q['searches']} جستجو، {q['phones']} شماره")
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[!] خطای دور: {e}")
            # خواب تا دور بعدی؛ ولی هر ۱s بیدار شو تا quit/release سریع باشد
            for _ in range(interval):
                if self.stop_event.is_set() or self.paused:
                    break
                time.sleep(1)
        print("👋 مانیتور تمام شد؛ همه وضعیت‌ها در دیتابیس و فایل‌های accounts ذخیره‌اند.")

    def stop(self) -> None:
        self.stop_event.set()
