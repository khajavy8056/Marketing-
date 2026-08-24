# -*- coding: utf-8 -*-
"""Brand, LAN listen, single-file Setup, English console."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from marketing_divar.brand import APP_ID, APP_NAME_EN, APP_NAME_FA, PORT
from marketing_divar.netinfo import lan_ipv4, listen_urls


class TestBranding(unittest.TestCase):
    def test_names(self):
        self.assertEqual(APP_NAME_EN, "Divar Marketing")
        self.assertEqual(APP_NAME_FA, "مارکتینگ دیوار")
        self.assertEqual(APP_ID, "DivarMarketing")
        self.assertEqual(PORT, 8642)

    def test_listen_urls_shape(self):
        info = listen_urls(8642)
        self.assertEqual(info["port"], 8642)
        self.assertEqual(info["bind"], "0.0.0.0")
        self.assertIn("127.0.0.1:8642", info["local"])
        self.assertIsInstance(info["lan"], list)
        self.assertIsInstance(lan_ipv4(), list)

    def test_logo_and_icon_pipeline(self):
        logo = os.path.join(ROOT, "marketing_divar", "web", "static", "logo.png")
        self.assertTrue(os.path.exists(logo))
        self.assertGreater(os.path.getsize(logo), 2000)
        ico = os.path.join(ROOT, "installer", "app.ico")
        self.assertTrue(os.path.exists(ico), "run png_to_ico.py")
        self.assertGreater(os.path.getsize(ico), 2000)

    def test_setup_app_is_english(self):
        path = os.path.join(ROOT, "installer", "setup_app.py")
        body = open(path, encoding="utf-8").read()
        self.assertIn("ttk.Progressbar", body)
        self.assertIn("DivarMarketing", body)
        self.assertIn("8642", body)
        self.assertIn("advfirewall", body)
        # no Persian letters in the installer source
        self.assertFalse(any("\u0600" <= ch <= "\u06FF" for ch in body))

    def test_console_entry_english(self):
        main = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
        self.assertIn("Press Enter", main)
        self.assertNotIn("یک کلید", main)
        banner = open(os.path.join(ROOT, "marketing_divar", "web", "__main__.py"),
                      encoding="utf-8").read()
        self.assertIn("0.0.0.0", banner)
        self.assertIn("Phone", banner)


if __name__ == "__main__":
    unittest.main()
