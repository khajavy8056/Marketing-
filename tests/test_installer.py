# -*- coding: utf-8 -*-
"""نصب ویندوز باید مثل نسخه‌های قبلی کامل باشد: نوار پیشرفت، سلامت، اجرا."""

import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


class TestWindowsInstaller(unittest.TestCase):
    def test_installer_has_full_progress_flow(self):
        with open(os.path.join(ROOT, "installer", "installer.ps1"),
                  encoding="utf-8-sig") as f:
            ps1 = f.read()
        for needle in (
            "ProgressBar",
            "DownloadProgressChanged",
            "Unblock-File",
            "main.py --check",
            "localhost:8642",
            ".venv",
            "CreateShortcut",
            "mirror-pypi",
            "Start Install",
            "شروع نصب",
        ):
            self.assertIn(needle, ps1, f"نصب‌کننده ناقص: {needle}")

    def test_entry_bats_call_installer(self):
        for name in ("Install-and-Run.bat", "شروع-دیوار-لید.bat"):
            with open(os.path.join(ROOT, name), encoding="utf-8",
                      errors="replace") as f:
                body = f.read()
            self.assertIn("installer.ps1", body)

    def test_selfcheck_includes_installer(self):
        from marketing_divar.selfcheck import run
        self.assertEqual(run(), 0)


if __name__ == "__main__":
    unittest.main()
