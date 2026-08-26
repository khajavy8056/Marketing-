# -*- coding: utf-8 -*-
"""Windows install must stay complete: progress bar, health check, launch."""

import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


class TestWindowsInstaller(unittest.TestCase):
    def test_installer_has_full_progress_flow(self):
        path = os.path.join(ROOT, "installer", "installer.ps1")
        raw = open(path, "rb").read()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "UTF-8 BOM required")
        self.assertIn(b"\r\n", raw, "installer.ps1 must be CRLF")
        with open(path, encoding="utf-8-sig") as f:
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
            "DivarMarketing",
            "divar-marketing-install.log",
            "Write-InstallLog",
            "--install-chromium",
            "ungoogled-chromium",
            "PROGRESS",
            "app-chromium",
            "barChrome",
            "SOURCE_FAIL",
            "BYTES",
            "SHA256",
            "CHROMIUM_START",
            "DOWNLOAD_COMPLETED",
            "FolderBrowserDialog",
            "Publish-AppFiles",
            "WindowStyle Minimized",
            "Install folder",
        ):
            self.assertIn(needle, ps1, f"installer missing: {needle}")
        self.assertFalse(any("\u0600" <= ch <= "\u06FF" for ch in ps1),
                         "installer GUI script must be English-only")

    def test_console_fallback_is_ascii_and_complete(self):
        path = os.path.join(ROOT, "installer", "install-console.ps1")
        raw = open(path, "rb").read()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        body = raw.decode("utf-8-sig")
        self.assertTrue(all(ord(c) < 128 for c in body), "console installer must be ASCII")
        for needle in ("Find-Python", "venv", "requirements.txt", "main.py --check",
                       "DivarMarketing", "localhost:8642", "mirror-pypi",
                       "--install-chromium", "app-chromium",
                       "ungoogled-chromium"):
            self.assertIn(needle, body)

    def test_entry_bats_are_windows_safe(self):
        for name in ("Install-and-Run.bat", "شروع-دیوار-لید.bat"):
            path = os.path.join(ROOT, name)
            raw = open(path, "rb").read()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), f"{name} missing BOM")
            self.assertIn(b"\r\n", raw, f"{name} must be CRLF")
            body = raw.decode("utf-8-sig", errors="replace")
            self.assertIn("installer.ps1", body)
            self.assertIn("install-console.ps1", body)
            self.assertIn("pause", body.lower())
            self.assertIn("Extract", body)

    def test_persian_bat_does_not_exit_on_broken_venv(self):
        path = os.path.join(ROOT, "شروع-دیوار-لید.bat")
        body = open(path, encoding="utf-8-sig").read()
        self.assertIn("import fastapi,uvicorn", body)
        self.assertIn("installer.ps1", body)

    def test_selfcheck_includes_installer(self):
        from marketing_divar.selfcheck import run
        self.assertEqual(run(), 0)


if __name__ == "__main__":
    unittest.main()
