# -*- coding: utf-8 -*-
"""Chromium اختصاصی برنامه — جدا از مرورگر کاربر و پوشهٔ موقت exe."""

import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from marketing_divar import app_chromium as ac  # noqa: E402
from marketing_divar.chromium_profile import (  # noqa: E402
    HOME_URL, launch_kwargs, save_profile, save_meta)


class TestBrowsersPath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = {
            k: os.environ.get(k)
            for k in ("DIVAR_DATA_DIR", "DIVAR_CHROMIUM_DIR",
                      "PLAYWRIGHT_BROWSERS_PATH")
        }
        os.environ["DIVAR_DATA_DIR"] = self.tmp
        os.environ.pop("DIVAR_CHROMIUM_DIR", None)

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_dir_is_under_app_data_not_mei(self):
        d = ac.browsers_dir()
        self.assertEqual(d, Path(self.tmp) / "app-chromium")
        self.assertNotIn("_MEI", str(d))
        ac.apply_browser_env()
        self.assertEqual(os.environ["PLAYWRIGHT_BROWSERS_PATH"], str(d))

    def test_finds_chrome_layout(self):
        root = Path(self.tmp) / "app-chromium"
        exe = root / "chromium-1155" / "chrome-win" / "chrome.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"fake")
        self.assertEqual(ac.find_chrome(root), exe)

    def test_rejects_mei_path(self):
        mei = Path(self.tmp) / "_MEI123" / "playwright" / "chromium-1155" / "chrome-win"
        mei.mkdir(parents=True)
        (mei / "chrome.exe").write_bytes(b"x")
        self.assertIsNone(ac.find_chrome(Path(self.tmp) / "_MEI123"))

    def test_extract_zip_layout(self):
        dest = Path(self.tmp) / "app-chromium"
        dest.mkdir()
        zpath = dest / "chromium-win64.zip"
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr("chrome-win/chrome.exe", b"bin")
        folder = dest / "chromium-1155"
        found = ac._extract_zip(zpath, folder, lambda m: None)
        self.assertTrue(found.is_file())
        self.assertTrue((folder / "INSTALLATION_COMPLETE").exists())
        self.assertEqual(ac.find_chrome(dest), found)

    def test_launch_kwargs_uses_app_chrome_not_channel(self):
        with mock.patch("marketing_divar.app_chromium.executable_path",
                        return_value="/opt/app/chrome"):
            kw = launch_kwargs(Path(self.tmp) / "prof")
        self.assertEqual(kw["executable_path"], "/opt/app/chrome")
        self.assertNotIn("channel", kw)
        self.assertEqual(kw["user_data_dir"], str(Path(self.tmp) / "prof"))
        self.assertFalse(kw["headless"])

    def test_save_profile_closes_window_when_logged_in(self):
        acc = Path(self.tmp) / "accounts"
        save_meta(str(acc), "acc1", {"phone": "09120000000"})
        cookies = [
            {"name": "sRefreshToken", "value": "R", "domain": ".divar.ir"},
            {"name": "sAccessToken", "value": "A", "domain": ".divar.ir"},
        ]
        with mock.patch("marketing_divar.chromium_profile.is_open",
                        return_value=True), \
             mock.patch("marketing_divar.chromium_profile._cookies_from_live",
                        return_value=cookies), \
             mock.patch("marketing_divar.chromium_profile.close_live") as cl:
            res = save_profile(str(acc), "acc1")
        self.assertTrue(res["ok"])
        self.assertTrue(res["ready"])
        cl.assert_called_once_with("acc1")
        from marketing_divar.chromium_profile import profile_ready
        self.assertTrue(profile_ready(str(acc), "acc1"))

    def test_ungoogled_zip_layout(self):
        dest = Path(self.tmp) / "app-chromium"
        dest.mkdir()
        zpath = dest / "u.zip"
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr("ungoogled-chromium_win/chrome.exe", b"bin")
        found = ac._extract_zip(zpath, dest / "current", lambda m: None)
        self.assertTrue(found.name.lower().startswith("chrome"))

    def test_github_urls_work_offline(self):
        with mock.patch.object(ac._fc, "_get", side_effect=OSError("offline")):
            urls = ac.github_zip_urls()
        self.assertTrue(any("ungoogled-chromium" in u for u in urls))
        self.assertTrue(any("github.com" in u for u in urls))

    def test_download_reports_percent(self):
        class Fake:
            headers = {"Content-Length": str(20 * 1024 * 1024)}
            def __init__(self):
                self.left = 20 * 1024 * 1024
            def read(self, n):
                if self.left <= 0:
                    return b""
                take = min(n, self.left)
                self.left -= take
                return b"x" * take
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        seen = []
        dest = Path(self.tmp) / "dl.zip"
        with mock.patch.object(ac._fc, "_get", return_value=Fake()):
            ac._fc._download("https://example.test/c.zip", dest,
                             lambda m: seen.append(m), lambda p: None)
        self.assertTrue(any(x.startswith("PROGRESS ") for x in seen))
        self.assertTrue(dest.exists())
        self.assertGreater(dest.stat().st_size, 8_000_000)

    def test_save_without_login_keeps_window(self):
        acc = Path(self.tmp) / "accounts"
        save_meta(str(acc), "acc1", {})
        with mock.patch("marketing_divar.chromium_profile.is_open",
                        return_value=True), \
             mock.patch("marketing_divar.chromium_profile._cookies_from_live",
                        return_value=[]), \
             mock.patch("marketing_divar.chromium_profile.close_live") as cl:
            res = save_profile(str(acc), "acc1")
        self.assertFalse(res["ok"])
        cl.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
