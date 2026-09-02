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
    """نصب‌کننده v3.9+/v4: payload رمزنگاری‌شده + مدل/کرومیوم داخل بسته."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    ps1_path = root / "installer" / "installer.ps1"
    if not ps1_path.is_file():
        raise FileNotFoundError("installer.ps1 missing")
    raw_ps1 = ps1_path.read_bytes()
    if not raw_ps1.startswith(b"\xef\xbb\xbf"):
        raise FileNotFoundError("installer.ps1 must be UTF-8 with BOM")
    ps1 = ps1_path.read_text(encoding="utf-8-sig")
    if "DivarMarketing" not in ps1:
        raise FileNotFoundError("installer.ps1 missing product id")
    bat = (root / "Install-and-Run.bat").read_text(encoding="utf-8-sig", errors="replace")
    if "installer.ps1" not in bat:
        raise FileNotFoundError("Install-and-Run.bat is not wired to installer.ps1")
    setup = (root / "installer" / "setup_app.py").read_text(encoding="utf-8")
    if "DivarMarketing" not in setup:
        raise FileNotFoundError("setup_app.py missing product id")
    if "nlu-model" not in setup:
        raise FileNotFoundError("setup_app.py missing nlu-model folder")
    if "app-chromium" not in setup:
        raise FileNotFoundError("setup_app.py missing app-chromium folder")
    if "Progressbar" not in setup and "ProgressBar" not in setup and "ttk.Progressbar" not in setup:
        raise FileNotFoundError("setup_app.py has no progress bar")
    fetch = root / "installer" / "fetch_chromium.py"
    if fetch.is_file():
        body = fetch.read_text(encoding="utf-8")
        if "ungoogled-chromium" not in body:
            raise FileNotFoundError("fetch_chromium.py incomplete")
        if "chrome-for-testing-public" in body or "CFT_WIN" in body:
            raise FileNotFoundError("fetch_chromium.py must not download Chrome for Testing")


def _check_static_ui() -> None:
    from pathlib import Path
    p = Path(__file__).parent / "web" / "static" / "index.html"
    html = p.read_text(encoding="utf-8")
    if not p.exists() or "مارکتینگ دیوار" not in html:
        raise FileNotFoundError(f"Persian panel file missing: {p}")
    if "kw-category" not in html:
        raise FileNotFoundError("category picker missing from panel")
    # شهرها اکنون آبشاری کشویی با تیک است — id قدیمی kw-city حذف شد
    if "city-dropdown" not in html and "kw-city" not in html:
        raise FileNotFoundError("city picker missing from panel (expected city-dropdown)")
    # اگر kw-city قدیمی بود، چک multiple، اگر جدید بود city-dropdown کافی است
    if "kw-city" in html:
        if 'id="kw-city" multiple' not in html and "id='kw-city' multiple" not in html:
            if "multiple size" not in html and "city-dropdown" not in html:
                raise FileNotFoundError("multi-city picker missing from panel")
    if "set-plat-divar" not in html or "set-plat-sheypoor" not in html:
        raise FileNotFoundError("platform enable switches missing from panel")
    if "kw-price-min" not in html:
        raise FileNotFoundError("price range missing from panel")
    if "kw-vip" not in html and "kw-hunter" not in html:
        raise FileNotFoundError("hunter / VIP missing from panel")
    if "hunter-adv-dlg" not in html or "hunterAdvOpen" not in html:
        raise FileNotFoundError("hunter advanced settings popup missing from panel")
    if "/api/hunter-profile" not in html:
        raise FileNotFoundError("hunter-profile API not wired in panel")
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
    if 'id="license-gate"' not in html or "lic-remember" not in html:
        raise FileNotFoundError("in-app license login missing from panel")
    if 'data-tab="profile"' not in html or "lic-bar" not in html:
        raise FileNotFoundError("subscription remaining-time bar missing from panel")
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
