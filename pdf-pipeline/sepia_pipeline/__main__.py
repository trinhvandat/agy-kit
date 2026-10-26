"""CLI mỏng cho sepia-pipeline: ``python -m sepia_pipeline <lệnh>``.

Lệnh: ``detect`` (Mốc 0 — phân loại) và ``convert`` (Mốc 1 — PDF → EPUB). CLI chỉ là lớp mỏng:
gọi hàm thuần trong các module rồi in.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Sequence

from . import PIPELINE_VERSION
from .convert import ConvertReport, convert_pdf
from .detect import SCAN_OCR, BookResult, detect_pdf


def format_human(result: BookResult) -> str:
    """Định dạng một BookResult cho người đọc."""
    lines = [result.path]
    if result.error is not None:
        lines.append(f"  error: {result.error}")
        return "\n".join(lines)
    dist = ", ".join(f"{label}={n}" for label, n in sorted(result.page_distribution.items()))
    fonts = ", ".join(result.legacy_fonts) if result.legacy_fonts else "—"
    scan_ocr = result.page_distribution.get(SCAN_OCR, 0)
    source = " / ".join(x for x in (result.producer, result.creator) if x) or "—"
    lines += [
        f"  loại chính : {result.label}",
        f"  số trang   : {result.n_pages}",
        f"  phân bố    : {dist or '—'}",
        f"  font legacy: {fonts}",
        f"  scan/scan_ocr/empty : {result.scan_pages} / {scan_ocr} / {result.empty_pages}",
        f"  nguồn (gợi ý): {source}",
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


def format_convert(report: ConvertReport) -> str:
    """Báo cáo ngắn cho một lần convert."""
    q = report.quality
    lines = [
        report.pdf_name,
        f"  → {report.epub.path}",
        f"  bookUid     : {report.epub.book_uid}",
        f"  engine      : {report.engine}",
        f"  pipeline_ver: {report.pipeline_version}",
        f"  trang       : {report.n_pages} (ảnh: {report.n_image_pages})"
        f"{'  [scan_ocr]' if report.is_scan_ocr else ''}",
        f"  chương/ảnh  : {report.epub.n_chapters} chương, {report.epub.n_images} ảnh nhúng",
        f"  đoạn/heading: {q.n_paragraphs} đoạn, {q.n_headings} heading"
        f" ({q.pct_short40:.0%} đoạn < 40 ký tự)",
        f"  ký tự rác   : {q.garbage_chars} ({q.garbage_ratio:.4f})",
        f"  khối rác bỏ : {q.garbage_blocks_removed} khối (điểm âm tiết Việt thấp)",
        f"  mục lục bỏ  : {q.printed_toc_removed} dòng",
        f"  epubcheck   : {q.epubcheck or '(chưa chạy)'}",
    ]
    if report.warnings:
        lines.append("  cảnh báo:")
        lines += [f"    - {w}" for w in report.warnings]
    return "\n".join(lines)


def _cmd_convert(args: argparse.Namespace) -> int:
    report = convert_pdf(
        args.input,
        args.output,
        font_profile=args.font_profile,
        engine=args.engine,
        run_check=not args.no_check,
    )
    if args.json:
        print(json.dumps(dataclasses.asdict(report), ensure_ascii=False, indent=2))
    else:
        print(format_convert(report))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sepia_pipeline",
        description=f"Sepia PDF pipeline (v{PIPELINE_VERSION}) — detect (Mốc 0), convert (Mốc 1).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_detect = sub.add_parser(
        "detect",
        help="Phân loại PDF theo trang/span (text_unicode/legacy/scan/empty/mixed).",
    )
    p_detect.add_argument("files", nargs="+", help="Một hoặc nhiều file .pdf")
    p_detect.add_argument("--json", action="store_true", help="In kết quả dạng JSON")
    p_detect.set_defaults(func=_cmd_detect)

    p_convert = sub.add_parser(
        "convert",
        help="Chuyển PDF → EPUB sạch (reflow, bỏ header/footer, TOC, trang ảnh).",
    )
    p_convert.add_argument("input", help="File .pdf đầu vào")
    p_convert.add_argument(
        "-o", "--output", default=None, help="File .epub ra (mặc định: pdf-pipeline/out/<tên>.epub)"
    )
    p_convert.add_argument(
        "--font-profile",
        default=None,
        help="Tên profile trong font_profiles.toml (vd dongy) để ghi font cụ thể vào CSS",
    )
    p_convert.add_argument(
        "--engine",
        choices=["auto", "heuristic", "docling"],
        default="auto",
        help="Engine trích: auto (docling cho scan_ocr) | heuristic | docling. Mặc định auto.",
    )
    p_convert.add_argument("--no-check", action="store_true", help="Bỏ qua epubcheck (nhanh hơn)")
    p_convert.add_argument("--json", action="store_true", help="In kết quả dạng JSON")
    p_convert.set_defaults(func=_cmd_convert)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
