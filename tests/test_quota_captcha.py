# -*- coding: utf-8 -*-
"""سقف نرم ۱۲۹ + ادامه تا کپچا + کپچای سادهٔ پنل."""

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
    def test_default_is_129(self):
        self.assertEqual(DEFAULTS["per_account_daily_limit"], 129)
        self.assertTrue(DEFAULTS["adaptive_until_captcha"])
        self.assertEqual(store.EDITABLE_SETTINGS["per_account_daily_limit"], 129)

    def test_legacy_60_migrates(self):
        db = os.path.join(tempfile.mkdtemp(), "q.db")
        store.settings_set(db, "telegram_chat_id", "x")  # create tables
        # شبیه‌سازی نصب قدیمی
        with store._con(db) as con:
            con.execute("DELETE FROM settings WHERE key='quota_soft_129'")
            con.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
                ("per_account_daily_limit", "60"))
            con.commit()
        s = store.settings_all(db)
        self.assertEqual(int(s["per_account_daily_limit"]), 129)

    def test_pick_hard_stop_vs_adaptive(self):
        tmp = tempfile.mkdtemp()
        acc = os.path.join(tmp, "acc", "a")
        os.makedirs(acc)
        json.dump({"token": "t"}, open(os.path.join(acc, "session.json"), "w"))
        db = os.path.join(tmp, "d.db")
        from marketing_divar.db import connect, bump_account_quota
        con = connect(db)
        for _ in range(129):
            bump_account_quota(con, "a")
        con.close()
        hard = AccountManager(
            {"per_account_daily_limit": 129, "adaptive_until_captcha": False},
            os.path.join(tmp, "acc"))
        self.assertIsNone(hard.pick(db))
        soft = AccountManager(
            {"per_account_daily_limit": 129, "adaptive_until_captcha": True},
            os.path.join(tmp, "acc"))
        self.assertEqual(soft.pick(db), "a")


if __name__ == "__main__":
    unittest.main()
