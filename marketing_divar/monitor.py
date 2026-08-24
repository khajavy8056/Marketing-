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
from .db import (bump_quota, chat_queue, connect, log_operation, mark_processing,
                 pending_phone, quota_today, reclaim_stuck_processing, set_phone)
from .matching import consider_new_lead
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

    def _refresh_notify(self) -> None:
        try:
            from . import store
            s = store.settings_all(self.db_path)
            self.cfg["notify"] = {
                "telegram_bot_token": s.get("telegram_bot_token") or "",
                "telegram_chat_id": s.get("telegram_chat_id") or "",
            }
        except Exception:
            pass

    def _tg(self, message: str) -> None:
        """اعلان تلگرام برای سرنخ/پیامک جدید — توکن جعلی را نمی‌زند."""
        try:
            self._refresh_notify()
            notify(self.cfg, message, important=False)
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
            self._anon = DivarClient(session_path=str(self.mgr.dir / "_anon" / "session.json"),
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
                        posts = self.anon.search(
                            "" if spec.get("match_all") else kw,
                            cities=cities, page=page,
                            category=spec.get("category") or None)
                        bump_quota(con, "searches", len(posts))
                    except DivarBlockedError as e:
                        notify(self.cfg, f"جستجو هم محدود شد!؟ ({e}) — "
                                         "watch_interval را در config.json بزرگ کنید",
                               problem="rate_limit/captcha", operation="search",
                               action="فاصله اسکن را زیاد کنید و وضعیت شبکه را بررسی کنید")
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
                    city = ",".join(str(c) for c in cities) if cities else "iran"
                    browse = bool(spec.get("match_all"))
                    if posts:
                        self._ev("info",
                                 f"جستجو «{kw}»"
                                 + (f" / دسته {spec.get('category')}" if spec.get("category") else "")
                                 + f": {len(posts)} آگهی")
                    for p in posts:
                        if consider_new_lead(con, self.anon, p, kw, city,
                                             match_all=browse):
                            new_total += 1
                            new_here += 1
                            t = str(p.get("title") or "")
                            where = ("دسته" if browse else
                                     ("عنوان" if kw in t else "متن"))
                            self._ev("info", f"🆕 سرنخ جدید: «{t[:40]}» "
                                             f"({where})")
                    con.commit()
                    if new_here == 0:
                        break  # صفحه بعدی تکراری
            return new_total
        finally:
            con.close()

    # ------------------------------------------------------- شماره‌گیری 📞 --
    def _maybe_sms(self, con, row, phone: str) -> None:
        """اگر گزینهٔ خودکار روشن باشد، همان لحظه از ملی‌پیامک پیامک می‌زند."""
        if not phone:
            return
        try:
            from . import store
            from .sms import live_sms_cfg, maybe_send_for_lead
            cfg = live_sms_cfg(self.db_path, self.cfg)
            for k in ("sms_provider", "sms_api_key", "sms_username", "sms_password",
                      "sms_line_number", "sms_auto_on_new", "sms_daily_limit"):
                self.cfg[k] = cfg.get(k)
            if not cfg.get("sms_auto_on_new"):
                return
            lim = int(cfg.get("sms_daily_limit") or 40)
            if quota_today(con).get("sms", 0) >= lim:
                self._ev("warning", "سقف پیامک امروز پر شد — پیامک ارسال نشد")
                return
            token = row["token"] if "token" in row.keys() else ""
            if token:
                try:
                    prev = con.execute("SELECT sms_status FROM leads WHERE token=?",
                                       (token,)).fetchone()
                    if prev and (prev["sms_status"] or "") == "sent":
                        return
                except Exception:
                    pass
            tpl = (store.template_get(self.db_path, "sms") or {}).get("text") or ""
            r = maybe_send_for_lead(cfg, {
                "title": row["title"] if "title" in row.keys() else "",
                "subtitle": row["subtitle"] if "subtitle" in row.keys() else "",
                "url": row["url"] if "url" in row.keys() else "",
                "phone": phone,
            }, tpl)
            if not r:
                return
            st = "sent" if r.get("ok") else "failed"
            if token:
                try:
                    con.execute("UPDATE leads SET sms_status=? WHERE token=?",
                                (st, token))
                    con.commit()
                except Exception:
                    pass
            if r.get("ok"):
                bump_quota(con, "sms")
                if token:
                    try:
                        from .db import now as _now
                        con.execute(
                            "UPDATE leads SET sms_status='sent', sms_sent_at=? WHERE token=?",
                            (_now(), token))
                        con.commit()
                    except Exception:
                        pass
                self._ev("success", f"پیامک خودکار ارسال شد → {phone}")
                print(f"  📩 پیامک خودکار: {phone}")
                qn = quota_today(con)
                self._tg(f"پیامک ارسال شد\nشماره: {phone}\n"
                         f"آگهی: {(row['title'] or '')[:60]}\n"
                         f"زمان ارسال: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                         f"پیامک امروز: {qn.get('sms', 0)}")
            else:
                self._ev("warning", f"پیامک خودکار ناموفق: {r.get('message')}")
        except Exception as e:
            self._ev("warning", f"پیامک: {e}")

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
                                     "اگر کپچاست: در مرورگر حل کنید و بنویسید: release <نام>",
                           problem="no_account", operation="contact",
                           action="اکانت کپچا/خطا را آزاد یا لاگین کنید")
                    self._notified_all_stuck = True
                return "wait"
            self._notified_all_stuck = False
            row = rows[0]
            cl = self.client_for(name)
            started = time.strftime("%Y-%m-%d %H:%M:%S")
            mark_processing(con, row["token"])
            try:
                res = cl.get_phone(row["token"])
            except DivarAuthError as e:
                con.execute("UPDATE leads SET phone_status='pending' WHERE token=?",
                            (row["token"],))
                con.commit()
                self.mgr.set_status(name, "relogin", note=str(e))
                self._ev("error", f"اکانت {name} نیاز به لاگین مجدد دارد")
                notify(self.cfg, f"اکانت {name} نیاز به لاگین مجدد دارد — "
                                 f"در ترمینال دیگر: accounts login {name}",
                       account=name, problem="authentication",
                       operation="contact", action=f"accounts login {name}")
                log_operation(con, token=row["token"], account=name,
                              operation="contact", result="auth_error",
                              error=str(e), started_at=started)
                return "wait"
            except DivarBlockedError as e:
                # این اکانت می‌ایستد؛ سرنخ به صف برمی‌گردد؛ بقیه ادامه می‌دهند
                con.execute("UPDATE leads SET phone_status='pending' WHERE token=?",
                            (row["token"],))
                con.commit()
                status = "captcha" if "کپچا" in str(e) or "captcha" in str(e).lower() \
                    else "cooldown"
                self.mgr.set_status(
                    name, status,
                    cooldown_sec=self.cfg.get("cooldown_on_block_min", 30) * 60,
                    note=f"{e} (status={e.status})")
                self._ev("warning" if status == "captcha" else "error",
                         f"اکانت {name} → {status} ({e}). بقیه اکانت‌ها ادامه می‌دهند")
                action = (f"در مرورگر divar.ir با همین اکانت کپچا را حل کنید "
                          f"سپس در پنل «آزادسازی {name}» را بزنید") if status == "captcha" \
                    else "صبر کنید تا سرد شدن تمام شود؛ اکانت‌های دیگر ادامه می‌دهند"
                notify(self.cfg, f"اکانت {name} → {status} ({e}). "
                                 f"بقیه اکانت‌ها ادامه می‌دهند. بعد از حل: release {name}",
                       account=name, problem=status, operation="contact",
                       action=action)
                log_operation(con, token=row["token"], account=name,
                              operation="contact", result=status,
                              error=str(e), started_at=started)
                return "wait"
            except Exception as e:
                con.execute(
                    "UPDATE leads SET phone_status='pending', last_error=?, "
                    "retry_count=retry_count+1 WHERE token=?",
                    (str(e)[:200], row["token"]))
                con.commit()
                log_operation(con, token=row["token"], account=name,
                              operation="contact", result="error",
                              error=str(e), started_at=started)
                self._ev("error", f"خطای شماره‌گیری {row['token']}: {e}")
                return "done"
            set_phone(con, row["token"], res)
            log_operation(con, token=row["token"], account=name,
                          operation="contact", result=res.get("status"),
                          phone=res.get("phone"), error=res.get("message"),
                          started_at=started)
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
                qn = quota_today(con)
                extracted = time.strftime("%Y-%m-%d %H:%M:%S")
                from .telegram_bot import found_alert_text
                self._tg(found_alert_text(row["title"] or "", res.get("phone") or "",
                                          extracted, int(qn.get("phones") or 0)))
                self._maybe_sms(con, row, res.get("phone") or "")
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
