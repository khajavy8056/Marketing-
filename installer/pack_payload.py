# -*- coding: utf-8 -*-
"""Build installer/payload.zip — every file the Setup EXE carries."""
from __future__ import annotations

import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "payload.zip"

SKIP_DIR = {
    ".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "build", "dist", "logs", "data", "node_modules",
}
SKIP_FILE = {"install-log.txt", "payload.zip"}
# Always include marketing_divar, main.py, installer, requirements.txt.


def _keep(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in SKIP_DIR for part in rel.parts):
        return False
    if path.name in SKIP_FILE or path.suffix in {".pyc", ".pyo"}:
        return False
    return True


def pack(dest: Path = OUT) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    count = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(ROOT):
            pdir = Path(dirpath)
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIR]
            for name in filenames:
                src = pdir / name
                if not _keep(src):
                    continue
                zf.write(src, src.relative_to(ROOT).as_posix())
                count += 1
    if dest.stat().st_size < 1000:
        raise RuntimeError("payload.zip is too small")
    print("Packed %d files -> %s (%d bytes)" % (count, dest, dest.stat().st_size))
    return dest


if __name__ == "__main__":
    pack()
