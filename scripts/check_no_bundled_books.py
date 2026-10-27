#!/usr/bin/env python3
"""CI guard: không được commit sách (.epub/.pdf) vào repo PUBLIC.

Cho phép fixture EPUB tự tạo dưới pdf-pipeline/tests/fixtures/. Fail nếu có file khác.
"""

import subprocess
import sys

ALLOW_PREFIX = "pdf-pipeline/tests/fixtures/"
EXTS = (".epub", ".pdf")


def main() -> int:
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    bad = [
        f
        for f in out
        if f.lower().endswith(EXTS) and not f.startswith(ALLOW_PREFIX)
    ]
    if bad:
        print("LỖI: sách có bản quyền KHÔNG được commit (repo public):", file=sys.stderr)
        for f in bad:
            print(f"  {f}", file=sys.stderr)
        return 1
    print("OK: không có .epub/.pdf nào bị track ngoài fixtures.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
