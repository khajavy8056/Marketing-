# -*- coding: utf-8 -*-
"""Write a Windows .ico that embeds the PNG (Vista+). ASCII only."""
import struct
import sys
from pathlib import Path


def png_to_ico(png_path: Path, ico_path: Path) -> None:
    data = png_path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit("not a PNG")
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(data), 22)
    ico_path.parent.mkdir(parents=True, exist_ok=True)
    ico_path.write_bytes(header + entry + data)


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    src = root / "marketing_divar" / "web" / "static" / "logo.png"
    dst = root / "installer" / "app.ico"
    if len(sys.argv) >= 3:
        src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    png_to_ico(src, dst)
    print("wrote", dst)
