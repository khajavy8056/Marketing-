# -*- coding: utf-8 -*-
"""پوشه پایدار داده — تنظیمات بعد از بستن برنامه باید بماند."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from marketing_divar.paths import apply_runtime_paths, migrate_legacy, user_data_dir
from marketing_divar import store


class TestPersistentPaths(unittest.TestCase):
    def test_migrate_and_keep_settings(self):
        tmp = Path(tempfile.mkdtemp())
        legacy = tmp / "app" / "data"
        legacy.mkdir(parents=True)
        dest = tmp / "stable"
        db = legacy / "divar_leads.db"
        from marketing_divar.db import connect
        con = connect(str(db))
        con.close()
        store.settings_set(str(db), "telegram_bot_token", "123:ABC")
        store.settings_set(str(db), "sms_username", "meli-user")
        (legacy / "accounts" / "ac1").mkdir(parents=True)
        (legacy / "accounts" / "ac1" / "session.json").write_text(
            '{"token":"t"}', encoding="utf-8")
        migrate_legacy(dest, cwd=tmp / "app")
        self.assertTrue((dest / "divar_leads.db").exists())
        self.assertTrue((dest / "accounts" / "ac1" / "session.json").exists())
        s = store.settings_all(str(dest / "divar_leads.db"))
        self.assertEqual(s["telegram_bot_token"], "123:ABC")
        self.assertEqual(s["sms_username"], "meli-user")
        # نصب دوباره نباید داده را پاک کند
        migrate_legacy(dest, cwd=tmp / "app")
        s2 = store.settings_all(str(dest / "divar_leads.db"))
        self.assertEqual(s2["telegram_bot_token"], "123:ABC")

    def test_apply_does_not_override_test_env(self):
        keys = ("DIVAR_DB_PATH", "DIVAR_DATA_DIR", "DIVAR_ACCOUNTS_DIR",
                "DIVAR_LOG_DIR", "DIVAR_CONFIG_PATH")
        old = {k: os.environ.get(k) for k in keys}
        tmp = tempfile.mkdtemp()
        os.environ["DIVAR_DATA_DIR"] = tmp
        os.environ["DIVAR_DB_PATH"] = "/tmp/keep-me.db"
        try:
            apply_runtime_paths()
            self.assertEqual(os.environ["DIVAR_DB_PATH"], "/tmp/keep-me.db")
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_user_data_dir_honors_override(self):
        old = os.environ.get("DIVAR_DATA_DIR")
        os.environ["DIVAR_DATA_DIR"] = "/tmp/khajavy-custom"
        try:
            self.assertEqual(str(user_data_dir()), "/tmp/khajavy-custom")
        finally:
            if old is None:
                os.environ.pop("DIVAR_DATA_DIR", None)
            else:
                os.environ["DIVAR_DATA_DIR"] = old


if __name__ == "__main__":
    unittest.main()
