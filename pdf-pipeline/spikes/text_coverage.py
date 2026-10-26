"""Đo độ phủ chữ (Mốc 1b, bước 1): lớp chữ PDF vs khối sẽ dựng EPUB, theo trang & theo engine.

uv run python spikes/text_coverage.py "../samples/<tên>.pdf" <heuristic|docling>
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pymupdf as fitz

from sepia_pipeline.detect import DetectConfig
from sepia_pipeline.extract import extract_document
from sepia_pipeline.quality import text_coverage_by_page
from sepia_pipeline.reflow import build_blocks


def _blocks(pdf: Path, engine: str):
    if engine == "docling":
        from sepia_pipeline.docling_adapter import extract_blocks_docling

        return extract_blocks_docling(pdf)
    d = fitz.open(str(pdf))
    try:
        doc = extract_document(d, pdf, DetectConfig())
    finally:
        d.close()
    return build_blocks(doc)


def main() -> int:
    pdf = Path(sys.argv[1])
    engine = sys.argv[2] if len(sys.argv) > 2 else "docling"
    t0 = time.time()
    blocks = _blocks(pdf, engine)
    dt = time.time() - t0
    rep = text_coverage_by_page(pdf, blocks)
    print(f"engine={engine}  thời gian trích={dt:.1f}s")
    print(
        f"tổng ký tự PDF={rep.total_pdf_chars}  khối={rep.total_block_chars}  "
        f"độ phủ={rep.coverage:.3f}"
    )
    print(f"số trang={rep.n_pages}  trang lớn nhất có khối={rep.max_block_page}")
    print(f"trang phủ <70%: {len(rep.low_pages)} | trang rỗng (có chữ PDF): {len(rep.empty_pages)}")
    print("  10 trang mất nhiều nhất:", sorted(rep.low_pages, key=lambda r: r[3])[:10])
    print("  trang rỗng:", rep.empty_pages[:20])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
