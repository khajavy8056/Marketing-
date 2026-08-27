# -*- coding: utf-8 -*-
"""Install health check. Console output is English only.

Run:  python main.py --check
Exit: 0 = OK | 1 = problem
"""

from __future__ import annotations

import sys

CHECKS = [
    ("requests library", lambda: __import__("requests")),
    ("fastapi library", lambda: __import__("fastapi")),
    ("uvicorn library", lambda: __import__("uvicorn")),
    ("Divar client module", lambda: __import__("marketing_divar.client")),
    ("monitor module", lambda: __import__("marketing_divar.monitor")),
    ("database module", lambda: __import__("marketing_divar.db")),
    ("web panel module", lambda: __import__("marketing_divar.web.server")),
    ("playwright library", lambda: __import__("playwright")),
    ("app Chromium helper", lambda: __import__("marketing_divar.app_chromium")),
]


def _check_windows_installer() -> None:
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    ps1 = (root / "installer" / "installer.ps1").read_text(encoding="utf-8-sig")
    console = (root / "installer" / "install-console.ps1").read_text(encoding="utf-8-sig")
    bat = (root / "Install-and-Run.bat").read_text(encoding="utf-8-sig", errors="replace")
    raw_ps1 = (root / "installer" / "installer.ps1").read_bytes()
    if not raw_ps1.startswith(b"\xef\xbb\xbf"):
        raise FileNotFoundError("installer.ps1 must be UTF-8 with BOM")
    for needle in ("ProgressBar", "DownloadProgressChanged", "Unblock-File",
                   "main.py --check", "localhost:8642", ".venv", "CreateShortcut",
                   "DivarMarketing", "divar-marketing-install.log",
                   "--install-chromium", "app-chromium",
                   "ungoogled-chromium", "PROGRESS",
                   "barChrome", "SOURCE_FAIL", "BYTES", "SHA256",
                   "CHROMIUM_START", "DOWNLOAD_COMPLETED",
                   "Find-Python", "Install-Python", "python.org",
                   "WindowStyle Minimized"):
        if needle not in ps1:
            raise FileNotFoundError(f"installer incomplete — missing {needle}")
    if "installer.ps1" not in bat or "install-console.ps1" not in bat:
        raise FileNotFoundError("Install-and-Run.bat is not wired to installers")
    if "Extract All" not in bat and "Extract the ZIP" not in bat:
        raise FileNotFoundError("Extract warning missing from bat")
    for needle in ("Find-Python", ".venv", "requirements.txt", "main.py --check",
                   "DivarMarketing", "localhost:8642",
                   "--install-chromium", "app-chromium",
                   "ungoogled-chromium"):
        if needle not in console:
            raise FileNotFoundError(f"console installer incomplete — missing {needle}")
    setup = (root / "installer" / "setup_app.py").read_text(encoding="utf-8")
    if "Progressbar" not in setup and "ProgressBar" not in setup:
        if "ttk.Progressbar" not in setup:
            raise FileNotFoundError("setup_app.py has no progress bar")
    if "DivarMarketing" not in setup:
        raise FileNotFoundError("setup_app.py missing product id")
    if "fetch_chromium" not in setup or "ungoogled-chromium" not in setup:
        raise FileNotFoundError("setup_app.py must download ungoogled-chromium")
    if "chrome_bar" not in setup or "CHROMIUM_START" not in setup:
        raise FileNotFoundError("setup_app.py missing independent Chromium progress")
    if "app-chromium" not in setup:
        raise FileNotFoundError("setup_app.py missing app-chromium folder")
    fetch = (root / "installer" / "fetch_chromium.py").read_text(encoding="utf-8")
    if "ungoogled-chromium" not in fetch or "PROGRESS" not in fetch:
        raise FileNotFoundError("fetch_chromium.py incomplete")
    for needle in ("SHA256", "SOURCE_FAIL", "BYTES", "SPEED",
                   "probe_url", "verify_zip", "CHROMIUM_START",
                   "INSTALLED.json", "zip_product", "chrome-for-testing",
                   "assert_chromium_zip", "DownloadManager", "RESUME",
                   "find_cached_zip", "ZIP_NAME", "Range"):
        if needle not in fetch:
            raise FileNotFoundError(f"fetch_chromium.py missing {needle}")
    if "SOURCE_MAX_SEC" in fetch:
        raise FileNotFoundError("SOURCE_MAX_SEC must not abort a live Chromium download")
    if "chrome-for-testing-public" in fetch or "CFT_WIN" in fetch:
        raise FileNotFoundError("fetch_chromium.py must not download Chrome for Testing")
    bat_setup = (root / "ساخت-نصب-استاندارد.bat").read_text(encoding="utf-8", errors="replace")
    if "fetch_chromium.py" not in bat_setup:
        raise FileNotFoundError("Setup build must bundle fetch_chromium.py")


def _check_static_ui() -> None:
    from pathlib import Path
    p = Path(__file__).parent / "web" / "static" / "index.html"
    html = p.read_text(encoding="utf-8")
    if not p.exists() or "مارکتینگ دیوار" not in html:
        raise FileNotFoundError(f"Persian panel file missing: {p}")
    if "kw-category" not in html:
        raise FileNotFoundError("category picker missing from panel")
    if "kw-city" not in html:
        raise FileNotFoundError("city picker missing from panel")
    if "kw-price-min" not in html or "kw-vip" not in html:
        raise FileNotFoundError("price range / VIP missing from panel")
    if "cap-dlg" not in html or "cap-answer" not in html:
        raise FileNotFoundError("in-panel captcha popup missing")
    if 'id="cap-frame"' in html or 'src="https://divar.ir"' in html:
        raise FileNotFoundError("iframe of divar.ir must not be used")
    if "openPuzzle" not in html or "/api/accounts/open-puzzle" not in html:
        raise FileNotFoundError("logged-in puzzle window missing from panel")
    if "createProfile" not in html or "/api/accounts/profile/create" not in html:
        raise FileNotFoundError("Chromium profile buttons missing from panel")
    if "/api/accounts/captcha-cleared" not in html or "capCleared" not in html:
        raise FileNotFoundError("captcha-cleared button missing from panel")
    if "/api/channels/test" not in html or "set-bale-on" not in html:
        raise FileNotFoundError("channel enable/test buttons missing from panel")
    if "divar.ir/user" not in html:
        raise FileNotFoundError("login URL divar.ir/user missing from panel")
    if 'id="boot-splash"' not in html or "در حال اتصال به سرورها" not in html:
        raise FileNotFoundError("boot splash missing from panel")
    if 'id="link-ping"' not in html or "BOOT_MS = 240000" not in html:
        raise FileNotFoundError("server-link badge / 4-minute splash missing")
    if 'id="quit-btn"' not in html or "quitApp" not in html:
        raise FileNotFoundError("panel exit button missing")
    if "/api/shutdown" not in html:
        raise FileNotFoundError("shutdown API not wired in panel")
    cp = Path(__file__).parent / "chromium_profile.py"
    src = cp.read_text(encoding="utf-8")
    if "--user-data-dir=" not in src or "--profile-directory=Default" not in src:
        raise FileNotFoundError("account Chromium must bind a named user-data-dir")
    if "--new-window" in src:
        raise FileNotFoundError("account launch must not use --new-window (steals panel profile)")
    if "_prepare_profile" not in src:
        raise FileNotFoundError("Chromium profile must be created before the window opens")
    if "_cookies_from_sqlite" not in src:
        raise FileNotFoundError("save must read on-disk Chromium cookies")
    logo = Path(__file__).parent / "web" / "static" / "logo.png"
    if not logo.exists() or logo.stat().st_size < 1000:
        raise FileNotFoundError("app logo missing")


def _check_db() -> None:
    from marketing_divar.db import connect
    con = connect("data/divar_leads.db")
    con.execute("SELECT COUNT(*) FROM leads").fetchone()
    con.close()


CHECKS += [
    ("Persian web panel + logo", _check_static_ui),
    ("database access (data/)", _check_db),
    ("Windows installer (progress + venv)", _check_windows_installer),
]


def run() -> int:
    print("Divar Marketing — health check")
    print("-" * 46)
    failed = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"  OK  {name}")
        except Exception as e:
            failed += 1
            print(f"  FAIL  {name} -> {e}")
    print("-" * 46)
    if failed:
        print(f"{failed} check(s) failed — see messages above")
        return 1
    print("All checks passed — ready to run")
    return 0


if __name__ == "__main__":
    sys.exit(run())
