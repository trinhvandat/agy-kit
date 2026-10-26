#!/usr/bin/env python3
"""Quét import trong assets/reader/ (foliate-js + bridge) và báo file bị thiếu.

Bắt cả import tĩnh (`import ... from './x.js'`, `import './x.js'`) lẫn động (`import('./x.js')`)
và `src="./x.js"` trong HTML. Chỉ xét specifier tương đối (bắt đầu bằng `.` hoặc `/`).

Chạy CI local:  python3 scripts/check_reader_imports.py
Thoát != 0 nếu có file thiếu (vd quên vendor/zip.js — lỗi làm sách không mở, không báo).
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
READER = ROOT / "androidApp" / "src" / "main" / "assets" / "reader"

# import ... from '<spec>' | import '<spec>' | import('<spec>') | src="<spec>"
PATTERNS = [
    re.compile(r"""import\s[^;'"]*?from\s*['"]([^'"]+)['"]"""),
    re.compile(r"""import\s*['"]([^'"]+)['"]"""),
    re.compile(r"""import\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""\bsrc\s*=\s*['"]([^'"]+)['"]"""),
]


def main() -> int:
    if not READER.is_dir():
        print(f"LỖI: không thấy {READER}", file=sys.stderr)
        return 2

    missing: list[str] = []
    dropped = 0
    scanned = 0
    for path in sorted(READER.rglob("*")):
        if path.suffix not in (".js", ".html"):
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            for pat in PATTERNS:
                for spec in pat.findall(line):
                    if not (spec.startswith(".") or spec.startswith("/")):
                        continue  # bỏ qua bare specifier (không có trong code này)
                    spec_clean = spec.split("?", 1)[0].split("#", 1)[0]
                    target = (path.parent / spec_clean).resolve()
                    # vendor/pdfjs CỐ Ý bỏ (chỉ cần cho PDF — Sepia chỉ đọc EPUB; pdf.js chỉ
                    # được import động khi mở PDF → đường EPUB không chạm). Xem foliate/VERSION.
                    if "vendor/pdfjs" in target.as_posix():
                        dropped += 1
                        continue
                    if not target.exists():
                        rel = path.relative_to(ROOT)
                        missing.append(f"{rel}:{lineno}  ->  {spec}  (thiếu {target})")

    if missing:
        print(f"THIẾU FILE import ({len(missing)}):", file=sys.stderr)
        for m in missing:
            print("  " + m, file=sys.stderr)
        return 1

    print(f"OK: {scanned} file, mọi import tương đối đều có file đích (bỏ qua {dropped} ref vendor/pdfjs cố ý).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
