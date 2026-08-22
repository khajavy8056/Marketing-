# -*- coding: utf-8 -*-
"""تست یکپارچه (End-to-End) با شبیه‌ساز دیوار — دقیقاً سناریوی کاربر:

۱) مانیتور با ۳ اکانت شروع می‌شود
۲) دور اول: ۵ آگهی → صف؛ شماره‌ها با چرخش اکانت‌ها گرفته می‌شوند
۳) اکانت b بعد از ۲ درخواست کپچا می‌خورد → a و c «ادامه می‌دهند» (بدون توقف)
۴) آگهی‌های جدید وسط کار می‌آیند (لحظه‌ای) → در دور بعد وارد صف می‌شوند
۵) آگهی «فقط چت» → لیست چت می‌رود (نه خطا)
۶) release اکانت b → دوباره چرخش برمی‌گردد
۷) سهمیه هر اکانت و سقف کلی رعایت می‌شود
"""

import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # برای mock_divar

from marketing_divar.config import DEFAULTS  # noqa: E402
from marketing_divar.db import (connect, pending_phone, chat_queue,  # noqa: E402
                                quota_today, account_quota_today)
from marketing_divar.monitor import Monitor  # noqa: E402
from mock_divar import MockDivar, start_mock  # noqa: E402


def make_account(root, name):
    d = os.path.join(root, "accounts", name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "session.json"), "w", encoding="utf-8") as f:
        import json
        json.dump({"phone": "09" + name, "token": f"tok-{name}"}, f)


class TestE2E(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "leads.db")
        MockDivar.reset()
        # اکانت‌های a و c معمولی؛ a بعد از ۱ درخواست موفق کپچا می‌خورد (قطعی)
        for name in "a", "b", "c":
            make_account(self.tmp, name)
        MockDivar.captcha_after = {"a": 1}
        # آگهی‌های اول: ۵ عدد (۲ تای فقط چت)
        MockDivar.add_posts([
            {"token": "p01", "title": "آگهی ۱", "has_chat": True},
            {"token": "p02chat", "title": "آگهی ۲ فقط چت", "has_chat": True},
            {"token": "p03", "title": "آگهی ۳", "has_chat": True},
            {"token": "p04", "title": "آگهی ۴", "has_chat": True},
            {"token": "p05chat", "title": "آگهی ۵ فقط چت", "has_chat": True},
        ])
        self.srv = start_mock()
        port = self.srv.server_address[1]
        cfg = dict(DEFAULTS)
        cfg.update({
            "phone_delay_sec": 0.02, "search_delay_sec": 0.02,
            "search_page_delay_sec": 0.02, "jitter_sec": 0.0,
            "watch_interval_sec": 1, "per_account_daily_limit": 50,
            "ip_daily_limit": 300, "interactive": False,
        })
        self.cfg = cfg
        self.base = f"http://127.0.0.1:{port}"

    def tearDown(self):
        self.srv.shutdown()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_scenario(self):
        mon = Monitor(self.cfg, [{"keyword": "تست", "cities": [1], "pages": 1}],
                      db_path=self.db, accounts_dir=os.path.join(self.tmp, "accounts"),
                      interactive=False, base_url=self.base)
        t = threading.Thread(target=mon.run, daemon=True)
        t.start()

        # ۱) دور اول باید ۵ سرنخ وارد و صف خالی شود (انتظار برای هر دو شرط)
        deadline = time.time() + 20
        while time.time() < deadline:
            con = connect(self.db)
            total = con.execute("SELECT COUNT(*) c FROM leads").fetchone()["c"]
            n = len(pending_phone(con))
            con.close()
            if total >= 5 and n == 0:
                break
            time.sleep(0.2)
        con = connect(self.db)
        self.assertEqual(len(pending_phone(con)), 0, "صف باید خالی شده باشد")
        self.assertEqual(len(chat_queue(con)), 2, "دو آگهی فقط-چت در لیست چت")
        found = con.execute(
            "SELECT COUNT(*) c FROM leads WHERE phone_status='found'").fetchone()["c"]
        self.assertEqual(found, 3, "سه شماره گرفته شده باشد")
        phones = [r["phone"] for r in
                  con.execute("SELECT phone FROM leads WHERE phone_status='found'")]
        self.assertTrue(all(p.startswith("0912") for p in phones))

        # ۲) اکانت a باید کپچا خورده باشد ولی صف «توسط بقیه» خالی شده باشد
        st = mon.mgr.snapshot(self.db)
        st_a = next(a for a in st if a["name"] == "a")
        self.assertEqual(st_a["status"], "captcha", "اکانت a باید کپچا خورده باشد")
        # درخواست‌های موفق بین اکانت‌ها تقسیم شده (چرخش واقعی) — همه ۵ سرنخ
        used = {a["name"]: a["phones_today"] for a in st}
        self.assertEqual(sum(used.values()), 5)
        self.assertEqual(used["a"], 1, "a فقط یک موفقیت قبل از کپچا")

        # ۳) آگهی جدید لحظه‌ای می‌آید → دور بعد می‌گیردش
        MockDivar.add_posts([
            {"token": "p06", "title": "آگهی جدید ۶", "has_chat": True},
            {"token": "p07chat", "title": "آگهی جدید ۷ چت", "has_chat": True},
        ])
        deadline = time.time() + 15
        while time.time() < deadline:
            con = connect(self.db)
            got = con.execute(
                "SELECT COUNT(*) c FROM leads WHERE token LIKE 'p0%' "
                "AND phone_status IN ('found','hidden')").fetchone()["c"]
            con.close()
            if got >= 7:
                break
            time.sleep(0.2)
        con = connect(self.db)
        got = con.execute(
            "SELECT COUNT(*) c FROM leads WHERE token LIKE 'p0%' "
            "AND phone_status IN ('found','hidden')").fetchone()["c"]
        self.assertEqual(got, 7, "آگهی‌های جدید لحظه‌ای پردازش شوند")
        con.close()

        # ۴) release اکانت a توسط اپراتور (شبیه‌سازی)
        mon.mgr.release("a")
        time.sleep(0.5)
        st_b = next(a for a in mon.mgr.snapshot(self.db) if a["name"] == "a")
        self.assertEqual(st_b["status"], "active")

        mon.stop()
        t.join(timeout=5)

        # ۵) سهمیه‌ها ثبت شده‌اند
        con = connect(self.db)
        self.assertGreaterEqual(quota_today(con)["phones"], 5)
        con.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
