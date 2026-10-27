"""SPIKE-5 (đo v4 → v5) — route scan_ocr HYBRID (Docling layout + Vision từ cache) trên CẢ CUỐN.

Đo theo brief PR scan-ocr-hybrid: CER/WER 3 trang GT, tỷ lệ âm tiết sai cấu trúc toàn cuốn, độ phủ
chữ, số heading, số dòng vắt khối, ảnh, thời gian, tất định (build 2 lần giống nhau), epubcheck.
So v4 (Docling + lớp chữ ẩn ABBYY) vs v5 (hybrid).

    cd pdf-pipeline
    uv sync --extra docling --extra ocr-mac   # cần Docling; cache đã có từ lệnh `ocr`
    uv run --with rapidfuzz python spikes/spike5_v5_measure.py "../samples/<tên>.pdf"
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import pymupdf as fitz

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spike5_cer_wer import GT_DIR, Levenshtein, match_window, norm, parse_gt  # noqa: E402

from sepia_pipeline import PIPELINE_VERSION  # noqa: E402
from sepia_pipeline.build_epub import build_epub  # noqa: E402
from sepia_pipeline.detect import DetectConfig  # noqa: E402
from sepia_pipeline.docling_adapter import extract_blocks_docling  # noqa: E402
from sepia_pipeline.extract import extract_document, sha256_file  # noqa: E402
from sepia_pipeline.model import Heading, ImageBlock, Paragraph  # noqa: E402
from sepia_pipeline.ocr_cache import DEFAULT_CACHE_DIR, read_cache  # noqa: E402
from sepia_pipeline.ocr_hybrid import extract_blocks_hybrid  # noqa: E402
from sepia_pipeline.quality import run_epubcheck, text_coverage_by_page  # noqa: E402
from sepia_pipeline.reflow import drop_garbage_blocks, drop_printed_toc  # noqa: E402
from sepia_pipeline.vietnamese import is_vietnamese_syllable, looks_vietnamese  # noqa: E402

GT_PAGES = [23, 101, 186]
OUT = Path("out/spike5_v5")
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def _post(blocks):
    """Hậu xử lý như convert (nguồn OCR + tiếng Việt): lọc rác âm tiết + bỏ mục lục in sẵn."""
    book_text = " ".join(b.text for b in blocks if isinstance(b, Heading | Paragraph))
    removed = 0
    if looks_vietnamese(book_text):
        g = drop_garbage_blocks(blocks)
        blocks, removed = g.kept, len(g.removed)
    blocks, toc = drop_printed_toc(blocks)
    return blocks, removed, toc


def _syllable_bad_pct(blocks) -> float:
    toks = _WORD.findall(" ".join(b.text for b in blocks if isinstance(b, Heading | Paragraph)))
    bad = sum(1 for t in toks if not is_vietnamese_syllable(t))
    return round(bad / len(toks) * 100, 2) if toks else 0.0


def _cer_wer(blocks, page0: int):
    txt = norm(
        " ".join(
            b.text
            for b in blocks
            if getattr(b, "page", 0) == page0 + 1 and isinstance(b, Heading | Paragraph)
        )
    )
    ec = gc = ew = gw = 0
    for b in parse_gt(GT_DIR / f"p{page0:04d}.txt"):
        h = match_window(b["text"], txt)
        ec += Levenshtein.distance(b["text"], h)
        gc += len(b["text"])
        ew += Levenshtein.distance(b["text"].split(), h.split())
        gw += len(b["text"].split())
    return (round(ec / gc * 100, 2) if gc else None, round(ew / gw * 100, 2) if gw else None)


def _measure(name, blocks, doc_model, pdf, extra: dict) -> dict:
    blocks, garbage, toc = _post(list(blocks))
    cov = text_coverage_by_page(pdf, blocks)
    row = {
        "variant": name,
        "headings": sum(1 for b in blocks if isinstance(b, Heading)),
        "paragraphs": sum(1 for b in blocks if isinstance(b, Paragraph)),
        "images": sum(1 for b in blocks if isinstance(b, ImageBlock)),
        "garbage_removed": garbage,
        "toc_removed": toc,
        "coverage_pct": round(cov.coverage * 100, 2),
        "syllable_bad_pct": _syllable_bad_pct(blocks),
        "cer_wer_gt": {p: _cer_wer(blocks, p) for p in GT_PAGES},
        **extra,
    }
    return row, blocks


def _build(doc_model, blocks, path) -> bytes:
    build_epub(doc_model, blocks, path, pipeline_version=PIPELINE_VERSION)
    return path.read_bytes()


def main() -> int:
    pdf = Path(sys.argv[1])
    OUT.mkdir(parents=True, exist_ok=True)
    cache = read_cache(DEFAULT_CACHE_DIR, sha256_file(pdf))
    assert cache is not None, "chưa có cache — chạy `sepia-pipeline ocr` trước"

    fdoc = fitz.open(str(pdf))
    doc_model = extract_document(fdoc, pdf, DetectConfig())
    fdoc.close()

    results = []
    # v5 hybrid (Docling #1)
    t0 = time.time()
    hblocks, hrep = extract_blocks_hybrid(pdf, cache)
    t_hybrid = round(time.time() - t0, 1)
    row5, blocks5 = _measure(
        "v5-hybrid",
        hblocks,
        doc_model,
        pdf,
        {
            "extract_sec": t_hybrid,
            "cross_block_lines": hrep.cross_block_lines,
            "floating_lines": hrep.floating_lines,
            "fallback_pages": len(hrep.fallback_pages),
            "vision_lines": hrep.vision_lines,
        },
    )
    # v4 docling + ABBYY (Docling #2)
    t0 = time.time()
    dblocks = extract_blocks_docling(pdf)
    t_v4 = round(time.time() - t0, 1)
    row4, _ = _measure("v4-abbyy", dblocks, doc_model, pdf, {"extract_sec": t_v4})
    results = [row4, row5]

    # Tất định v5: build 2 lần (Docling #3 cho blocks lần 2) → byte-identical
    t0 = time.time()
    hblocks2, _ = extract_blocks_hybrid(pdf, cache)
    blocks5b, _, _ = _post(list(hblocks2))
    b1 = _build(doc_model, blocks5, OUT / "v5_a.epub")
    b2 = _build(doc_model, blocks5b, OUT / "v5_b.epub")
    deterministic = b1 == b2
    epubcheck = run_epubcheck(str(OUT / "v5_a.epub"))

    summary = {
        "pipeline_version": PIPELINE_VERSION,
        "deterministic_build": deterministic,
        "epubcheck": epubcheck,
        "results": results,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")

    # Xuất text 3 trang GT theo thứ tự đọc v5 (để spot-check reading order + đối chiếu ảnh).
    for p in GT_PAGES:
        txt = "\n".join(
            b.text for b in blocks5 if getattr(b, "page", 0) == p + 1 and hasattr(b, "text")
        )
        (OUT / f"p{p:04d}_v5.txt").write_text(txt, encoding="utf-8")

    print(f"PIPELINE_VERSION={PIPELINE_VERSION} | tất định={deterministic} | {epubcheck}\n")
    hdr = (
        f"{'variant':10} {'head':>5} {'para':>5} {'img':>5} "
        f"{'cov%':>7} {'syl_bad%':>9} {'extract_s':>10}"
    )
    print(hdr)
    for r in results:
        print(
            f"{r['variant']:10} {r['headings']:>5} {r['paragraphs']:>5} {r['images']:>5} "
            f"{r['coverage_pct']:>7} {r['syllable_bad_pct']:>9} {r['extract_sec']:>10}"
        )
    print("\nCER/WER 3 trang GT (CER%, WER%):")
    for r in results:
        print(f"  {r['variant']}: " + "  ".join(f"p{p}={r['cer_wer_gt'][p]}" for p in GT_PAGES))
    print(
        f"\nv5: cross_block={row5['cross_block_lines']} floating={row5['floating_lines']} "
        f"fallback_pages={row5['fallback_pages']} vision_lines={row5['vision_lines']}"
    )
    print("→ out/spike5_v5/summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
