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
                   "DivarMarketing", "divar-marketing-install.log"):
        if needle not in ps1:
            raise FileNotFoundError(f"installer incomplete — missing {needle}")
    if "installer.ps1" not in bat or "install-console.ps1" not in bat:
        raise FileNotFoundError("Install-and-Run.bat is not wired to installers")
    if "Extract All" not in bat and "Extract the ZIP" not in bat:
        raise FileNotFoundError("Extract warning missing from bat")
    for needle in ("Find-Python", ".venv", "requirements.txt", "main.py --check",
                   "DivarMarketing", "localhost:8642"):
        if needle not in console:
            raise FileNotFoundError(f"console installer incomplete — missing {needle}")
    setup = (root / "installer" / "setup_app.py").read_text(encoding="utf-8")
    if "Progressbar" not in setup and "ProgressBar" not in setup:
        if "ttk.Progressbar" not in setup:
            raise FileNotFoundError("setup_app.py has no progress bar")
    if "DivarMarketing" not in setup:
        raise FileNotFoundError("setup_app.py missing product id")


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
    if "cap-dlg" not in html or "cap-live-frame" not in html or "capProbe" not in html:
        raise FileNotFoundError("in-panel verification popup missing")
    if 'id="cap-frame"' in html or 'src="https://divar.ir"' in html:
        raise FileNotFoundError("iframe of divar.ir must not be used")
    if "openPuzzle" not in html or "/api/accounts/open-puzzle" not in html:
        raise FileNotFoundError("logged-in puzzle window missing from panel")
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
