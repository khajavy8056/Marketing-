# -*- coding: utf-8 -*-
"""سقف نرم ۶۰ + ادامه تا کپچا + کپچای سادهٔ پنل."""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from marketing_divar.accounts import AccountManager
from marketing_divar.config import DEFAULTS
from marketing_divar.gate import check_answer, new_challenge, to_fa
from marketing_divar import store


class TestGateCaptcha(unittest.TestCase):
    def test_persian_math(self):
        ch = {"expect": 12, "question": f"{to_fa(5)} + {to_fa(7)}"}
        self.assertTrue(check_answer(ch, "12"))
        self.assertTrue(check_answer(ch, "۱۲"))
        self.assertFalse(check_answer(ch, "11"))
        self.assertFalse(check_answer({}, "12"))
        q = new_challenge("ac1")
        self.assertEqual(q["expect"], q["a"] + q["b"])


class TestSoftQuota(unittest.TestCase):
    def test_default_is_60_and_45(self):
        self.assertEqual(DEFAULTS["per_account_daily_limit"], 60)
        self.assertEqual(DEFAULTS["phone_delay_sec"], 45)
        self.assertEqual(DEFAULTS["watch_interval_sec"], 300)
        self.assertTrue(DEFAULTS["adaptive_until_captcha"])
        self.assertEqual(store.EDITABLE_SETTINGS["per_account_daily_limit"], 60)
        self.assertEqual(store.EDITABLE_SETTINGS["phone_delay_sec"], 45)
        self.assertEqual(store.EDITABLE_SETTINGS["watch_interval_sec"], 300)

    def test_legacy_129_migrates_to_60(self):
        db = os.path.join(tempfile.mkdtemp(), "q.db")
        store.settings_set(db, "telegram_chat_id", "x")
        with store._con(db) as con:
            con.execute("DELETE FROM settings WHERE key='defaults_2_1_23'")
            con.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
                ("per_account_daily_limit", "129"))
            con.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
                ("phone_delay_sec", "10"))
            con.commit()
        s = store.settings_all(db)
        self.assertEqual(int(s["per_account_daily_limit"]), 60)
        self.assertEqual(float(s["phone_delay_sec"]), 45)

    def test_custom_quota_is_kept(self):
        db = os.path.join(tempfile.mkdtemp(), "q.db")
        store.settings_set(db, "per_account_daily_limit", 80)
        store.settings_set(db, "phone_delay_sec", 20)
        s = store.settings_all(db)
        self.assertEqual(int(s["per_account_daily_limit"]), 80)
        self.assertEqual(float(s["phone_delay_sec"]), 20)

    def test_legacy_60_stays_60(self):
        db = os.path.join(tempfile.mkdtemp(), "q.db")
        store.settings_set(db, "telegram_chat_id", "x")
        with store._con(db) as con:
            con.execute("DELETE FROM settings WHERE key='defaults_2_1_23'")
            con.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
                ("per_account_daily_limit", "60"))
            con.commit()
        s = store.settings_all(db)
        self.assertEqual(int(s["per_account_daily_limit"]), 60)

    def test_pick_hard_stop_vs_adaptive(self):
        tmp = tempfile.mkdtemp()
        acc = os.path.join(tmp, "acc", "a")
        os.makedirs(acc)
        json.dump({"token": "t"}, open(os.path.join(acc, "session.json"), "w"))
        db = os.path.join(tmp, "d.db")
        from marketing_divar.db import connect, bump_account_quota
        con = connect(db)
        for _ in range(60):
            bump_account_quota(con, "a")
        con.close()
        hard = AccountManager(
            {"per_account_daily_limit": 60, "adaptive_until_captcha": False},
            os.path.join(tmp, "acc"))
        self.assertIsNone(hard.pick(db))
        soft = AccountManager(
            {"per_account_daily_limit": 60, "adaptive_until_captcha": True},
            os.path.join(tmp, "acc"))
        self.assertEqual(soft.pick(db), "a")


if __name__ == "__main__":
    unittest.main()
