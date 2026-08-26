# -*- coding: utf-8 -*-
"""Chromium اختصاصی برنامه — جدا از مرورگر کاربر و پوشهٔ موقت exe."""

import os
import sys
import tempfile
import time
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

    def test_ignores_system_chrome_outside_app_dir(self):
        system = Path(self.tmp) / "Program Files" / "Google" / "Chrome" / "Application"
        system.mkdir(parents=True)
        (system / "chrome.exe").write_bytes(b"system")
        app = Path(self.tmp) / "app-chromium"
        app.mkdir()
        self.assertIsNone(ac.find_chrome(app))
        self.assertNotEqual(ac.find_chrome(app), system / "chrome.exe")

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
        self.assertTrue(any(x.startswith("BYTES ") for x in seen))
        self.assertTrue(any(x.startswith("SPEED ") for x in seen))
        self.assertTrue(any(x == "DOWNLOAD_COMPLETED" for x in seen))
        self.assertTrue(dest.exists())
        self.assertGreater(dest.stat().st_size, 8_000_000)

    def test_incomplete_download_deleted(self):
        class Tiny:
            headers = {"Content-Length": "100"}
            def read(self, n):
                return b""
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        dest = Path(self.tmp) / "small.zip"
        with mock.patch.object(ac._fc, "_get", return_value=Tiny()):
            with self.assertRaises(RuntimeError):
                ac._fc._download("https://example.test/bad.zip", dest,
                                 lambda m: None, None)
        self.assertFalse(dest.exists())
        self.assertFalse((dest.with_suffix(".zip.part")).exists())

    def test_sha256_mismatch_deletes(self):
        class Fake:
            headers = {"Content-Length": str(9 * 1024 * 1024)}
            def __init__(self):
                self.left = 9 * 1024 * 1024
            def read(self, n):
                if self.left <= 0:
                    return b""
                take = min(n, self.left)
                self.left -= take
                return b"y" * take
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        dest = Path(self.tmp) / "hash.zip"
        with mock.patch.object(ac._fc, "_get", return_value=Fake()):
            with self.assertRaises(RuntimeError) as ctx:
                ac._fc._download("https://example.test/h.zip", dest,
                                 lambda m: None, None,
                                 expected_sha256="0" * 64)
        self.assertIn("SHA256", str(ctx.exception))
        self.assertFalse(dest.exists())

    def test_verify_zip_crc(self):
        zpath = Path(self.tmp) / "ok.zip"
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr("chrome-win/chrome.exe", b"bin" * 100)
        # below min size
        with self.assertRaises(RuntimeError):
            ac._fc.verify_zip(zpath, min_bytes=8_000_000)
        ac._fc.verify_zip(zpath, min_bytes=10)
        junk = Path(self.tmp) / "trunc.zip"
        junk.write_bytes(b"PK\x03\x04not-a-real-zip")
        with self.assertRaises(RuntimeError):
            ac._fc.verify_zip(junk, min_bytes=4)

    def test_dead_source_skipped_quickly(self):
        t0 = time.time()
        ok = ac._fc.probe_url("http://127.0.0.1:1/nope.zip", timeout=1.5)
        dt = time.time() - t0
        self.assertFalse(ok)
        self.assertLess(dt, 5.0)

    def test_ensure_falls_through_dead_then_ok(self):
        dest = Path(self.tmp) / "app-chromium"
        dest.mkdir()
        os.environ["DIVAR_CHROMIUM_DIR"] = str(dest)
        zpath = Path(self.tmp) / "good.zip"
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr("chrome-win/chrome.exe", b"bin")
        # pad to min size after extract path: _download min 8MB so we mock
        # ensure_installed at source loop
        srcs = [
            {"name": "dead", "url": "http://127.0.0.1:1/a.zip", "kind": "x"},
            {"name": "ok", "url": "https://example.test/ok.zip", "kind": "x"},
        ]
        notes = []

        def fake_download(url, dest_zip, log, progress, expected_sha256=None,
                          min_bytes=8_000_000):
            dest_zip.write_bytes(zpath.read_bytes())
            log("PROGRESS 100")
            log("DOWNLOAD_COMPLETED")

        with mock.patch.object(ac._fc, "sources", return_value=srcs), \
             mock.patch.object(ac._fc, "github_zip_urls", return_value=[]), \
             mock.patch.object(ac._fc, "probe_url",
                               side_effect=lambda u, timeout=6: "ok.zip" in u), \
             mock.patch.object(ac._fc, "_download", side_effect=fake_download), \
             mock.patch.object(ac._fc, "verify_zip", return_value=None):
            found = ac._fc.ensure_installed(log=notes.append)
        self.assertTrue(found.is_file())
        self.assertTrue(any("SOURCE_FAIL dead" in n for n in notes))
        self.assertTrue(any(n.startswith("CHROMIUM_OK") or "ready" in n.lower()
                            for n in notes))

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

    def test_status_and_parse(self):
        ac._parse_log("CHROMIUM_START")
        ac._parse_log("SOURCE ghproxy")
        ac._parse_log("PROGRESS 42")
        ac._parse_log("BYTES 1000/2000")
        ac._parse_log("SPEED 1.20 MB/s")
        st = ac.status()
        self.assertEqual(st["percent"], 42)
        self.assertEqual(st["bytes"], 1000)
        self.assertEqual(st["source"], "ghproxy")


if __name__ == "__main__":
    unittest.main(verbosity=2)
