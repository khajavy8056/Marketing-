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

import os
import threading
import time
from typing import Any, Dict, List, Optional

from .accounts import AccountManager
from .client import DivarAuthError, DivarBlockedError, DivarClient
from .db import (account_quota_today, bump_quota, chat_queue, connect,
                 log_operation, mark_processing, pending_phone, quota_today,
                 reclaim_stuck_processing, set_phone)
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
        self._acct_errors: Dict[str, int] = {}

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
                "telegram_api_base": s.get("telegram_api_base") or "",
                "telegram_proxy": s.get("telegram_proxy") or "",
                "bale_bot_token": s.get("bale_bot_token") or "",
                "bale_chat_id": s.get("bale_chat_id") or "",
                "rubika_bot_token": s.get("rubika_bot_token") or "",
                "rubika_chat_id": s.get("rubika_chat_id") or "",
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

    def _vip_on(self) -> bool:
        try:
            from . import store
            return bool(store.settings_all(self.db_path).get("vip_telegram", True))
        except Exception:
            return True

    def _vip_found(self, post: Dict[str, Any], spec: Dict[str, Any], city: str,
                   phone: str = "") -> None:
        if not self._vip_on():
            return
        try:
            from .telegram_bot import vip_alert_text
            from .cities import title_of_city
            from .categories import title_of
            cities = spec.get("cities") or []
            city_name = title_of_city(cities[0]) if cities else (city or "همه ایران")
            self._tg(vip_alert_text(
                title=str(post.get("title") or ""),
                city=city_name,
                category=title_of(spec.get("category") or "") or "",
                price=post.get("price") or 0,
                url=str(post.get("url") or ""),
                phone=phone or "",
            ))
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

    def _search_platforms(self, q: str, cities_arg, page: int, cat) -> List[Dict[str, Any]]:
        try:
            from . import store as _st
            from .platforms import enabled_from_settings
            plats = enabled_from_settings(_st.settings_all(self.db_path))
        except Exception:
            plats = ["divar"]
        posts: List[Dict[str, Any]] = []
        if "divar" in plats:
            posts.extend(self.anon.search(
                q, cities=cities_arg, page=page, category=cat) or [])
        if "sheypoor" in plats:
            try:
                from . import sheypoor as _sh
                posts.extend(_sh.search(
                    self.anon, q, cities=cities_arg, page=page,
                    category=cat) or [])
            except Exception:
                pass
        if "ring" in plats:
            try:
                from . import ring as _rg
                posts.extend(_rg.search(
                    self.anon, q, cities=cities_arg, page=page,
                    category=cat) or [])
            except Exception:
                pass
        return posts

    # ------------------------------------------------------------ جستجو 🔎 --
    def watch_once(self) -> int:
        """یک دور جستجوی همه کلمه‌کلیدی‌ها؛ تعداد سرنخ جدید را برمی‌گرداند."""
        con = connect(self.db_path)
        new_total = 0
        try:
            for spec in self.keywords:
                kw = spec["keyword"]
                cities = spec.get("cities")
                city_ids = list(cities) if cities else [None]
                pages = int(spec.get("pages", 1))
                for city_id in city_ids:
                    cities_arg = None if city_id in (None, 0, "0") else [city_id]
                    for page in range(1, pages + 1):
                        posts: List[Dict[str, Any]] = []
                        cat = spec.get("category") or None
                        try:
                            q = "" if spec.get("match_all") else kw
                            posts = self._search_platforms(q, cities_arg, page, cat)
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
                            if any(k in type(e).__name__ for k in
                                   ("Proxy", "Connect", "Timeout", "SSLError")) \
                                    or "proxy" in str(e).lower():
                                hint = (" — اتصال برقرار نشد؛ VPN/پروکسی و "
                                        "اینترنت را بررسی کنید")
                            print(f"[!] جستجو «{kw}» صفحه {page}: {e}{hint}")
                            self._ev("error", f"خطای جستجوی «{kw}»: {e}{hint}")
                            break
                        new_here = 0
                        city = ",".join(str(c) for c in cities) if cities else "iran"
                        browse = bool(spec.get("match_all"))
                        if posts:
                            self._ev("info",
                                     f"جستجو «{kw}»"
                                     + (f" / دسته {spec.get('category')}"
                                        if spec.get("category") else "")
                                     + f": {len(posts)} آگهی")
                        for p in posts:
                            p = dict(p)
                            if cat:
                                p.setdefault("category", cat)
                            if consider_new_lead(
                                    con, self.anon, p, kw, city,
                                    match_all=browse,
                                    price_min=int(spec.get("price_min") or 0),
                                    price_max=int(spec.get("price_max") or 0),
                                    vip=bool(spec.get("vip"))):
                                if spec.get("hunter") and not p.get("hunter_block"):
                                    try:
                                        self._score_hunter(con, p, spec, kw, city)
                                    except Exception:
                                        pass
                                new_total += 1
                                new_here += 1
                                t = str(p.get("title") or "")
                                where = ("دسته" if browse else
                                         ("عنوان" if kw in t else "متن"))
                                mark = "⭐ ویژه " if spec.get("vip") else ""
                                self._ev("info", f"🆕 {mark}سرنخ جدید: «{t[:40]}» "
                                                 f"({where})")
                                if spec.get("vip"):
                                    self._vip_found(p, spec, city)
                        con.commit()
                        if new_here == 0:
                            break
            return new_total
        finally:
            con.close()

    # ------------------------------------------------------- شماره‌گیری 📞 --
    def _score_hunter(self, con, post: Dict[str, Any], spec: Dict[str, Any],
                      kw: str, city: str) -> None:
        from .categories import hunter_allowed
        from .hunter import collect_samples, evaluate
        from .hunter_profile import default_profile, merge_overrides
        from . import store as _st2
        cat = spec.get("category") or post.get("category") or ""
        if not hunter_allowed(cat) and cat:
            return
        prof = merge_overrides(default_profile(str(cat), kw),
                               spec.get("hunter_adv") or {})
        if not prof.get("hunter"):
            return
        extra = dict(post)
        extra["keyword"] = kw
        extra["category"] = cat
        blob = " ".join(str(post.get(k) or "") for k in
                        ("title", "subtitle", "description", "inspect_summary"))
        plat = str(post.get("platform") or "divar")
        samples = collect_samples(con, kw, city, plat)
        sc = evaluate(int(post.get("price") or 0), samples,
                      _st2.settings_all(self.db_path), extra=extra,
                      profile=prof, text=blob)
        token = post.get("token")
        if not token or sc.get("blocked"):
            return
        level = sc.get("level") or ""
        if sc.get("pending"):
            level = "pending"
        elif not sc.get("warm") or level in ("none", "suspicious", "market"):
            if not sc.get("pending"):
                if level == "market":
                    level = ""
        try:
            con.execute(
                "UPDATE leads SET hunter_level=?, hunter_adj_pct=?, hunter_questions=? "
                "WHERE token=?",
                (level, float(sc.get("adj_pct") or 0),
                 str(sc.get("questions") or "")[:400], token))
        except Exception:
            con.execute("UPDATE leads SET hunter_level=? WHERE token=?",
                        (level, token))
        if sc.get("pending") or level == "pending":
            try:
                con.execute(
                    "UPDATE leads SET inquiry_status='pending' WHERE token=? "
                    "AND COALESCE(inquiry_status,'')=''",
                    (token,))
            except Exception:
                pass
        post["hunter_level"] = level
        post["hunter_questions"] = sc.get("questions") or ""

    def _row_get(self, row, key, default=""):
        try:
            if hasattr(row, "keys") and key in row.keys():
                v = row[key]
                return default if v is None else v
        except Exception:
            pass
        if isinstance(row, dict):
            return row.get(key, default)
        return default

    def _maybe_hunter_inquire(self, con, row, phone: str = "",
                              account_name: str = "") -> None:
        """جای‌خالی شکارچی: اگر شماره هست پیامک، وگرنه چت. وضعیت: در انتظار تصمیم."""
        token = self._row_get(row, "token")
        if not token:
            return
        hl = str(self._row_get(row, "hunter_level") or "")
        inq = str(self._row_get(row, "inquiry_status") or "")
        if hl != "pending" and inq not in ("pending",):
            return
        if inq == "sent":
            return
        from . import store
        from .db import now as _now
        questions = str(self._row_get(row, "hunter_questions") or "")
        tpl = (store.template_get(self.db_path, "inquire") or {}).get("text") or ""
        lead = {
            "title": self._row_get(row, "title"),
            "subtitle": self._row_get(row, "subtitle"),
            "url": self._row_get(row, "url"),
            "city": self._row_get(row, "city"),
            "keyword": self._row_get(row, "keyword"),
            "price": self._row_get(row, "price", 0),
            "published_at": self._row_get(row, "published_at"),
            "platform": self._row_get(row, "platform") or "divar",
            "token": token,
            "questions": questions,
            "hunter_questions": questions,
            "phone": phone or self._row_get(row, "phone"),
        }
        if lead["phone"]:
            try:
                from .sms import live_sms_cfg, send_for_lead, sms_ready
                cfg = live_sms_cfg(self.db_path, self.cfg)
                ready, _why = sms_ready(cfg)
                if ready:
                    lim = int(cfg.get("sms_daily_limit") or 40)
                    if quota_today(con).get("sms", 0) < lim:
                        r = send_for_lead(cfg, lead, tpl)
                        if r and r.get("ok"):
                            con.execute(
                                "UPDATE leads SET inquiry_status='sent', sms_status='sent', "
                                "sms_sent_at=? WHERE token=?",
                                (_now(), token))
                            bump_quota(con, "sms")
                            con.commit()
                            self._ev("success", "استعلام شکارچی پیامک شد")
                            return
            except Exception as e:
                self._ev("warning", f"استعلام پیامک: {e}")
        # چت
        try:
            from .chat import compose_chat, send_divar_chat
            lim = 40
            try:
                lim = int(store.settings_all(self.db_path).get("chat_auto_daily_limit") or 40)
            except Exception:
                pass
            if quota_today(con).get("chats", 0) >= lim:
                return
            name = account_name or self.mgr.pick(self.db_path)
            if not name:
                return
            text = compose_chat(tpl, lead)
            cl = self.client_for(name)

            def _send(_c, tok, msg):
                from .chat_browser import send_for_token
                return send_for_token(
                    tok, msg, client=_c,
                    accounts_dir=str(self.mgr.dir), account=name,
                    url=lead.get("url") or "")

            r = send_divar_chat(cl, token, text, send_fn=_send)
            if r.get("ok"):
                con.execute(
                    "UPDATE leads SET inquiry_status='sent', chat_status='sent', "
                    "chat_sent_at=?, chat_account=? WHERE token=?",
                    (_now(), name, token))
                bump_quota(con, "chats")
                con.commit()
                self._ev("success", "استعلام شکارچی در چت ارسال شد")
            elif r.get("status") == "removed":
                con.execute(
                    "UPDATE leads SET phone_status='removed', inquiry_status='gone' "
                    "WHERE token=?", (token,))
                con.commit()
        except Exception as e:
            self._ev("warning", f"استعلام چت: {e}")

    def drain_hunter_inquire(self, max_items: int = 6) -> None:
        con = connect(self.db_path)
        try:
            try:
                rows = con.execute(
                    "SELECT * FROM leads WHERE hunter_level='pending' "
                    "AND COALESCE(inquiry_status,'') IN ('','pending') "
                    "AND COALESCE(phone_status,'') != 'removed' "
                    "ORDER BY id DESC LIMIT ?", (max_items,)).fetchall()
            except Exception:
                rows = []
        finally:
            con.close()
        for row in rows:
            if self.stop_event.is_set():
                return
            con = connect(self.db_path)
            try:
                phone = ""
                try:
                    if "phone_status" in row.keys() and row["phone_status"] == "found":
                        phone = row["phone"] or ""
                except Exception:
                    pass
                self._maybe_hunter_inquire(con, row, phone=phone)
            finally:
                con.close()

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

    def _maybe_chat(self, con, row, account_name: str) -> None:
        """چت خودکار برای فقط‌چت — متن با {title} متغیر است."""
        try:
            from . import store
            from .chat import compose_chat, send_divar_chat
            from .db import now as _now
            s = store.settings_all(self.db_path)
            if not s.get("chat_auto_on_new"):
                return
            lim = int(s.get("chat_auto_daily_limit") or 40)
            if quota_today(con).get("chats", 0) >= lim:
                self._ev("warning", "سقف چت خودکار امروز پر شد")
                return
            token = row["token"] if "token" in row.keys() else ""
            if not token:
                return
            try:
                if (row["phone_status"] if "phone_status" in row.keys() else "") == "found":
                    return  # شماره هست → پیامک، نه چت
            except Exception:
                pass
            prev = con.execute("SELECT chat_status FROM leads WHERE token=?",
                               (token,)).fetchone()
            if prev and (prev["chat_status"] or "") == "sent":
                return
            delay = float(s.get("chat_auto_delay_sec") or 90)
            if os.environ.get("DIVAR_BASE_URL"):
                delay = 0
            if delay > 0:
                time.sleep(min(delay, 120))
            tpl = (store.template_get(self.db_path, "chat") or {}).get("text") or ""
            lead = {
                "title": row["title"] if "title" in row.keys() else "",
                "subtitle": row["subtitle"] if "subtitle" in row.keys() else "",
                "url": row["url"] if "url" in row.keys() else "",
                "city": row["city"] if "city" in row.keys() else "",
                "keyword": row["keyword"] if "keyword" in row.keys() else "",
                "price": row["price"] if "price" in row.keys() else 0,
                "published_at": row["published_at"] if "published_at" in row.keys() else "",
                "platform": row["platform"] if "platform" in row.keys() else "divar",
                "token": token,
            }
            text = compose_chat(tpl, lead)
            cl = self.client_for(account_name)

            def _send(_c, tok, msg):
                from .chat_browser import send_for_token
                return send_for_token(
                    tok, msg, client=_c,
                    accounts_dir=str(self.mgr.dir), account=account_name,
                    url=lead.get("url") or "")

            r = send_divar_chat(cl, token, text, send_fn=_send)
            st = "sent" if r.get("ok") else (r.get("status") or "requires_operator")
            now_s = _now()
            if st == "removed":
                con.execute(
                    "UPDATE leads SET phone_status='removed', chat_status='removed', "
                    "removed_reason=?, last_error=? WHERE token=?",
                    ("chat_gone", (r.get("message") or "")[:200], token))
                con.commit()
                self._ev("info", "آگهی/چت حذف شده — بدون خطا رد شد: %s" % (lead.get("title") or "")[:40])
                return
            con.execute(
                "UPDATE leads SET chat_status=?, lead_status=?, chat_sent_at=?, "
                "chat_account=?, chat_thread_id=? WHERE token=?",
                (st, "contacted" if r.get("ok") else "new",
                 now_s if r.get("ok") else "", account_name,
                 r.get("thread_id") or "", token))
            log_operation(con, token=token, account=account_name, operation="chat",
                          result=st, error="" if r.get("ok") else r.get("message"),
                          started_at=now_s)
            con.commit()
            if r.get("ok"):
                bump_quota(con, "chats")
                self._ev("success", "💬 چت خودکار ارسال شد (%s)" % account_name)
            else:
                self._ev("warning", "چت خودکار ناموفق — اپراتور: %s" % r.get("message"))
        except Exception as e:
            self._ev("warning", f"چت خودکار: {e}")

    def drain_chat(self, max_items: int = 8) -> None:
        """صف فقط‌چت باقی‌مانده را با تیک خودکار خالی می‌کند."""
        try:
            from . import store
            s = store.settings_all(self.db_path)
            if not s.get("chat_auto_on_new"):
                return
        except Exception:
            return
        con = connect(self.db_path)
        try:
            rows = chat_queue(con, limit=max_items)
        finally:
            con.close()
        for row in rows:
            if self.stop_event.is_set():
                return
            name = self.mgr.pick(self.db_path)
            if not name:
                return
            con = connect(self.db_path)
            try:
                self._maybe_chat(con, row, name)
            finally:
                con.close()

    def poll_inboxes(self) -> None:
        """خواندن پاسخ چت (همان آگهی) و صندوق پیامک ملی‌پیامک."""
        from . import store
        s = store.settings_all(self.db_path)
        con = connect(self.db_path)
        try:
            if s.get("sms_inbox_on") and s.get("sms_provider") == "melipayamak":
                from .sms import live_sms_cfg, receive_melipayamak
                from .inbox import ingest_sms
                cfg = live_sms_cfg(self.db_path, self.cfg)
                rec = receive_melipayamak(
                    cfg.get("sms_username") or "",
                    cfg.get("sms_password") or cfg.get("sms_api_key") or "")
                for m in rec.get("messages") or []:
                    ingest_sms(con, m.get("from") or "", m.get("body") or "",
                               m.get("date") or "",
                               use_llm=bool(s.get("nlu_use_local", True)))
            # چت: سرنخ‌های ارسال‌شده را یکی‌یکی می‌خواند (تطبیق thread_id)
            if s.get("chat_auto_on_new"):
                from .chat_browser import read_thread
                from .inbox import ingest_chat
                rows = con.execute(
                    "SELECT * FROM leads WHERE (chat_status='sent' "
                    "OR inquiry_status='sent') "
                    "AND COALESCE(phone_status,'') != 'removed' "
                    "ORDER BY id DESC LIMIT 6").fetchall()
                acc = self.mgr.pick(self.db_path)
                if acc:
                    for row in rows:
                        url = row["url"] if "url" in row.keys() else ""
                        token = row["token"]
                        if not url:
                            continue
                        th = read_thread(url, str(self.mgr.dir), acc, token=token)
                        if th.get("status") == "removed":
                            con.execute(
                                "UPDATE leads SET phone_status='removed', "
                                "removed_reason='chat_gone' WHERE token=?", (token,))
                            con.commit()
                            self._ev("info", "چت آگهی دیگر در دسترس نیست: %s" % token[:16])
                            continue
                        ingest_chat(con, th, use_llm=bool(s.get("nlu_use_local", True)))
        finally:
            con.close()

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
            soft = int(self.cfg.get("per_account_daily_limit", 60) or 60)
            used = account_quota_today(con, name)
            if used >= soft and self.cfg.get("adaptive_until_captcha", True):
                extra = float(self.cfg.get("phone_delay_sec", 10) or 10)
                self._ev("info",
                         f"سقف نرم {soft} برای {name} رد شد — با فاصله بیشتر ادامه تا دیوار کپچا بخواهد")
                time.sleep(max(extra, 0))
            cl = self.client_for(name)
            started = time.strftime("%Y-%m-%d %H:%M:%S")
            mark_processing(con, row["token"])
            try:
                from .contact import get_contact
                from .platforms import split_token
                plat, _nid = split_token(row["token"])
                ad_url = row["url"] if "url" in row.keys() else ""
                res = get_contact(
                    row["token"], client=cl if plat == "divar" else None,
                    accounts_dir=str(self.mgr.dir), account=name,
                    url=ad_url or "")
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
                # این اکانت می‌ایستد؛ سرنخ در صف شماره می‌ماند
                con.execute("UPDATE leads SET phone_status='pending', last_error=? WHERE token=?",
                            (str(e)[:200], row["token"]))
                con.commit()
                # ۴۰۳/۴۲۹ تماس = محدودیت شماره — پاپ‌آپ آزادسازی، نه «فقط چت»
                status = "captcha"
                self.mgr.set_status(
                    name, status,
                    cooldown_sec=self.cfg.get("cooldown_on_block_min", 30) * 60,
                    note=f"{e} (status={e.status})")
                self.mgr.record_block(
                    name, getattr(e, "body", "") or "",
                    token=row["token"],
                    url=(row["url"] if "url" in row.keys() else "") or "")
                self._ev("warning",
                         f"اکانت {name} محدود شد ({e}). آگهی در صف شماره ماند.")
                action = (f"در پنل پاپ‌آپ را حل کنید یا دیوار را باز کنید "
                          f"سپس «آزادسازی {name}» را بزنید")
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
            st = res.get("status")
            if st == "error":
                con.execute(
                    "UPDATE leads SET phone_status='pending', last_error=?, "
                    "retry_count=retry_count+1 WHERE token=?",
                    ((res.get("message") or "شماره گرفته نشد")[:200], row["token"]))
                con.commit()
                log_operation(con, token=row["token"], account=name,
                              operation="contact", result="error",
                              error=res.get("message"), started_at=started)
                self._acct_errors[name] = self._acct_errors.get(name, 0) + 1
                self._ev("warning",
                         f"شماره گرفته نشد — در صف ماند: {str(row['title'] or '')[:40]}")
                if self._acct_errors[name] >= 2:
                    self.mgr.set_status(
                        name, "captcha",
                        note=res.get("message") or "محدودیت شماره — آزادسازی کنید")
                    self._ev("warning",
                             f"اکانت {name} به آزادسازی نیاز دارد (شماره پشت‌سرهم گرفته نشد)")
                    return "wait"
                return "done"
            set_phone(con, row["token"], res)
            log_operation(con, token=row["token"], account=name,
                          operation="contact", result=st,
                          phone=res.get("phone"), error=res.get("message"),
                          started_at=started)
            bump_quota(con, "phones")
            self._acct_errors[name] = 0
            if st == "found":
                self._ev("success", f"📞 شماره پیدا شد: {row['title'][:40]} → {res['phone']}")
            elif st == "hidden":
                self._ev("info", f"💬 فقط چت (دیوار صریحاً مخفی کرد): {row['title'][:40]}")
            self.mgr.record_use(self.db_path, name)
            con.commit()
            if st == "found":
                print(f"  📞 ✓ {name}: {row['title'][:32]} → {res['phone']}")
                qn = quota_today(con)
                extracted = time.strftime("%Y-%m-%d %H:%M:%S")
                from .telegram_bot import found_alert_text
                self._tg(found_alert_text(row["title"] or "", res.get("phone") or "",
                                          extracted, int(qn.get("phones") or 0)))
                is_vip = False
                try:
                    is_vip = bool(row["vip"]) if "vip" in row.keys() else False
                except Exception:
                    is_vip = False
                if is_vip:
                    self._vip_found({"title": row["title"] if "title" in row.keys() else "",
                                     "url": row["url"] if "url" in row.keys() else "",
                                     "price": row["price"] if "price" in row.keys() else 0},
                                    {"cities": None, "category": ""},
                                    row["city"] if "city" in row.keys() else "",
                                    phone=res.get("phone") or "")
                try:
                    if (row["hunter_level"] if "hunter_level" in row.keys() else "") == "pending":
                        self._maybe_hunter_inquire(con, row, phone=res.get("phone") or "",
                                                   account_name=name)
                    else:
                        self._maybe_sms(con, row, res.get("phone") or "")
                except Exception:
                    self._maybe_sms(con, row, res.get("phone") or "")
            elif st == "hidden":
                print(f"  💬 − {name}: {row['title'][:32]} → فقط چت (رفت به لیست چت)")
                try:
                    self._maybe_chat(con, row, name)
                except Exception as e:
                    self._ev("warning", f"چت خودکار: {e}")
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
                # تا آزادسازی صبر کن؛ اگر اکانت آزاد شد همان‌جا صف را ادامه بده
                for _ in range(90):
                    if self.stop_event.is_set():
                        return
                    time.sleep(2)
                    if self.mgr.pick(self.db_path):
                        break
                else:
                    return
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
                try:
                    self.drain_chat()
                except Exception as e:
                    self._ev("warning", f"صف چت: {e}")
                try:
                    self.drain_hunter_inquire()
                except Exception as e:
                    self._ev("warning", f"استعلام شکارچی: {e}")
                try:
                    self.poll_inboxes()
                except Exception as e:
                    self._ev("warning", f"صندوق پاسخ: {e}")
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
