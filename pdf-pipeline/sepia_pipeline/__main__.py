"""CLI mỏng cho sepia-pipeline: ``python -m sepia_pipeline <lệnh>``.

Mốc 0 chỉ có lệnh ``detect``. CLI chỉ là lớp mỏng: gọi hàm thuần trong ``detect`` rồi in.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Sequence

from . import PIPELINE_VERSION
from .detect import BookResult, detect_pdf


def format_human(result: BookResult) -> str:
    """Định dạng một BookResult cho người đọc."""
    lines = [result.path]
    if result.error is not None:
        lines.append(f"  error: {result.error}")
        return "\n".join(lines)
    dist = ", ".join(f"{label}={n}" for label, n in sorted(result.page_distribution.items()))
    fonts = ", ".join(result.legacy_fonts) if result.legacy_fonts else "—"
    lines += [
        f"  loại chính : {result.label}",
        f"  số trang   : {result.n_pages}",
        f"  phân bố    : {dist or '—'}",
        f"  font legacy: {fonts}",
        f"  scan/empty : {result.scan_pages} / {result.empty_pages}",
    ]
    return "\n".join(lines)


def _result_to_dict(result: BookResult) -> dict:
    return dataclasses.asdict(result)


def _cmd_detect(args: argparse.Namespace) -> int:
    results = [detect_pdf(path) for path in args.files]
    if args.json:
        print(json.dumps([_result_to_dict(r) for r in results], ensure_ascii=False, indent=2))
    else:
        print("\n\n".join(format_human(r) for r in results))
    return 1 if any(r.error for r in results) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sepia_pipeline",
        description=f"Sepia PDF pipeline (v{PIPELINE_VERSION}) — Mốc 0: detect.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_detect = sub.add_parser(
        "detect",
        help="Phân loại PDF theo trang/span (text_unicode/legacy/scan/empty/mixed).",
    )
    p_detect.add_argument("files", nargs="+", help="Một hoặc nhiều file .pdf")
    p_detect.add_argument("--json", action="store_true", help="In kết quả dạng JSON")
    p_detect.set_defaults(func=_cmd_detect)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
