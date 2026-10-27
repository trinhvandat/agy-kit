"""Phân tích phân bố heading + kích thước chương để thiết kế chia nhỏ file (v8, display-qa).

Chạy pipeline hybrid tới `blocks` (như convert.py), in: histogram heading theo cấp, tổng ký tự,
số file hiện tại (`_blocks_to_chapters`), và kích thước từng chương (ký tự).

    cd pdf-pipeline && uv run python spikes/analyze_chapters.py "../samples/<ten>.pdf"
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf as fitz

from sepia_pipeline.build_epub import _blocks_to_chapters
from sepia_pipeline.detect import DetectConfig
from sepia_pipeline.extract import extract_document
from sepia_pipeline.model import Heading, ImageBlock, Paragraph, Table
from sepia_pipeline.ocr_cache import DEFAULT_CACHE_DIR, read_cache
from sepia_pipeline.ocr_hybrid import extract_blocks_hybrid
from sepia_pipeline.reflow import ReflowConfig, drop_garbage_blocks, drop_printed_toc
from sepia_pipeline.vietnamese import looks_vietnamese


def _block_chars(b) -> int:
    if isinstance(b, Table):
        return sum(len(c) for row in b.rows for c in row)
    if isinstance(b, ImageBlock):
        return len(b.caption or "")
    return len(getattr(b, "text", "") or "")


def main() -> int:
    pdf = Path(sys.argv[1])
    cache = read_cache(
        DEFAULT_CACHE_DIR, __import__("hashlib").sha256(pdf.read_bytes()).hexdigest()
    )
    assert cache is not None, "chưa có cache"
    fdoc = fitz.open(str(pdf))
    doc_model = extract_document(fdoc, pdf, DetectConfig())
    fdoc.close()

    blocks, _ = extract_blocks_hybrid(pdf, cache)
    cfg = ReflowConfig()
    book_text = " ".join(b.text for b in blocks if isinstance(b, Heading | Paragraph))
    if looks_vietnamese(book_text):
        blocks = drop_garbage_blocks(blocks, cfg).kept
    blocks, _toc = drop_printed_toc(blocks, cfg)

    hist = {1: 0, 2: 0, 3: 0}
    for b in blocks:
        if isinstance(b, Heading):
            hist[min(max(b.level, 1), 3)] += 1
    total_chars = sum(_block_chars(b) for b in blocks)
    n_blocks = len(blocks)
    n_tables = sum(1 for b in blocks if isinstance(b, Table))
    n_images = sum(1 for b in blocks if isinstance(b, ImageBlock))

    chapters, images, nav = _blocks_to_chapters(doc_model, blocks)
    # ký tự mỗi chương hiện tại (ước theo độ dài html_body)
    sizes = sorted((len(c.html_body) for c in chapters), reverse=True)

    print(f"TỔNG: blocks={n_blocks} ký_tự={total_chars} bảng={n_tables} ảnh={n_images}")
    print(f"HEADING theo cấp: h1={hist[1]} h2={hist[2]} h3={hist[3]}")
    print(f"CHƯƠNG hiện tại (_blocks_to_chapters): {len(chapters)} file, {len(images)} ảnh")
    print(f"  kích thước html_body (byte) top: {sizes[:10]}")
    print(f"  tổng html_body byte={sum(len(c.html_body) for c in chapters)}")
    print(f"  mục tiêu ~10k ký tự/file → ước {total_chars // 10000}–{total_chars // 7000} file")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
