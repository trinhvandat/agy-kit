"""Dựng EPUB v9 (sạch hiển thị — issue #20) + kiểm cổng → out/v9/ + summary.json (clean-display).

Khác build_v8: (1) bỏ đồ đạc (tiêu đề chạy + số trang) ngay trong extract_blocks_hybrid → bất biến
B = assigned + floating + **furniture** = tổng dòng cache; (2) đổi "»"/"®" dẫn đầu → "• "; (3) đo
SỐ ĐẾM hiển thị trên EPUB cuối: tiêu đề chạy còn sót, dòng mục lục in sẵn còn sót, ký tự » ® _.

    cd pdf-pipeline && uv run --with rapidfuzz python spikes/build_v9.py "../samples/<ten>.pdf"
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

import pymupdf as fitz

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spike5_v51_measure import _block_text, _nonspace, _toks  # noqa: E402

from sepia_pipeline import PIPELINE_VERSION  # noqa: E402
from sepia_pipeline.build_epub import build_epub  # noqa: E402
from sepia_pipeline.detect import DetectConfig  # noqa: E402
from sepia_pipeline.extract import extract_document, sha256_file  # noqa: E402
from sepia_pipeline.model import Heading, ImageBlock, Paragraph, Table  # noqa: E402
from sepia_pipeline.ocr_cache import DEFAULT_CACHE_DIR, read_cache  # noqa: E402
from sepia_pipeline.ocr_hybrid import extract_blocks_hybrid  # noqa: E402
from sepia_pipeline.quality import run_epubcheck  # noqa: E402
from sepia_pipeline.reflow import (  # noqa: E402
    ReflowConfig,
    _is_toc_entry_text,
    drop_garbage_blocks,
    drop_printed_toc,
    tidy_bullet_markers,
)
from sepia_pipeline.vietnamese import looks_vietnamese  # noqa: E402

OUT = Path("out/v9")


def _xhtml_char_counts(epub_path: Path) -> list[int]:
    counts = []
    with zipfile.ZipFile(epub_path) as z:
        for name in sorted(n for n in z.namelist() if "chap_" in n and n.endswith(".xhtml")):
            html = z.read(name).decode("utf-8")
            counts.append(len(re.sub(r"<[^>]+>", "", html)))
    return counts


def main() -> int:
    pdf = Path(sys.argv[1])
    OUT.mkdir(parents=True, exist_ok=True)
    cache = read_cache(DEFAULT_CACHE_DIR, sha256_file(pdf))
    assert cache is not None, "chưa có cache — chạy `sepia-pipeline ocr` trước"
    cache_words = {p.page: set(_toks(" ".join(ln.text for ln in p.lines))) for p in cache.pages}
    cache_nonspace = sum(_nonspace(ln.text) for p in cache.pages for ln in p.lines)

    fdoc = fitz.open(str(pdf))
    doc_model = extract_document(fdoc, pdf, DetectConfig())
    fdoc.close()

    blocks, hybrid = extract_blocks_hybrid(pdf, cache)
    blocks = tidy_bullet_markers(blocks)
    cfg = ReflowConfig()
    book_text = " ".join(b.text for b in blocks if isinstance(b, Heading | Paragraph))
    if looks_vietnamese(book_text):
        blocks = drop_garbage_blocks(blocks, cfg).kept
    blocks, toc_removed = drop_printed_toc(blocks, cfg)

    # --- Bất biến A (từ khối trang-cache ⊆ cache) + B (assigned + floating + furniture = cache) ---
    outside = 0
    for b in blocks:
        p0 = getattr(b, "page", 0) - 1
        if p0 not in cache_words:
            continue
        outside += sum(1 for w in _toks(_block_text(b)) if w not in cache_words[p0])
    inv_a_ok = outside == 0
    inv_b_ok = (
        hybrid.assigned_lines + hybrid.floating_lines + hybrid.furniture_lines
        == hybrid.vision_lines
        == cache.n_lines
    )

    full_text = " ".join(_block_text(b) for b in blocks)
    final_nonspace = _nonspace(full_text)

    # --- SỐ ĐẾM hiển thị còn sót trên EPUB cuối (mục tiêu ≈ 0) ---
    para_head = [b for b in blocks if isinstance(b, Heading | Paragraph)]
    running_header_leak = sum(
        1 for b in para_head if re.search(r"tự học đông y", b.text, re.IGNORECASE)
    )
    toc_leak = sum(1 for b in para_head if _is_toc_entry_text(b.text))
    char_counts_strange = {
        "»": full_text.count("»"),
        "®": full_text.count("®"),
        "_": full_text.count("_"),
        "•": full_text.count("•"),
    }

    # --- Dựng EPUB v9 hai lần (tất định) ---
    a, b_ = OUT / "book.epub", OUT / "book_b.epub"
    rep = build_epub(doc_model, blocks, a, pipeline_version=PIPELINE_VERSION)
    build_epub(doc_model, blocks, b_, pipeline_version=PIPELINE_VERSION)
    deterministic = a.read_bytes() == b_.read_bytes()
    b_.unlink()
    epubcheck = run_epubcheck(str(a))

    char_counts = _xhtml_char_counts(a)
    n_files = len(char_counts)
    over_11k = sum(1 for c in char_counts if c > 11000)
    n_wide_tables = sum(
        1 for b in blocks if isinstance(b, Table) and max(len(r) for r in b.rows) >= 4
    )

    summary = {
        "pipeline_version": PIPELINE_VERSION,
        "n_xhtml_files": n_files,
        "n_images": rep.n_images,
        "file_chars": {
            "min": min(char_counts) if char_counts else 0,
            "max": max(char_counts) if char_counts else 0,
            "mean": round(sum(char_counts) / n_files) if n_files else 0,
            "over_11k": over_11k,
            "top10": sorted(char_counts, reverse=True)[:10],
        },
        "target_40_80_files": 40 <= n_files <= 80,
        "deterministic_build": deterministic,
        "epubcheck": epubcheck,
        "invariants": {
            "A_cached_words_subset_cache": inv_a_ok,
            "outside_source_words": outside,
            "B_assigned_floating_furniture_eq_cache": inv_b_ok,
        },
        "lines": {
            "vision": hybrid.vision_lines,
            "assigned": hybrid.assigned_lines,
            "floating": hybrid.floating_lines,
            "furniture": hybrid.furniture_lines,
        },
        "furniture_examples": list(hybrid.furniture_examples[:40]),
        "display_counts_after": {
            "running_header_leak": running_header_leak,
            "printed_toc_leak": toc_leak,
            "printed_toc_removed": toc_removed,
            "strange_chars": char_counts_strange,
            "wide_tables": n_wide_tables,
        },
        "chars": {
            "final_nonspace": final_nonspace,
            "cache_nonspace": cache_nonspace,
            "final_le_cache": final_nonspace <= cache_nonspace,
        },
        "counts": {
            "headings": sum(1 for b in blocks if isinstance(b, Heading)),
            "paragraphs": sum(1 for b in blocks if isinstance(b, Paragraph)),
            "images": sum(1 for b in blocks if isinstance(b, ImageBlock)),
            "tables": sum(1 for b in blocks if isinstance(b, Table)),
        },
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")

    print(f"PIPELINE_VERSION={PIPELINE_VERSION}")
    print(
        f"file XHTML={n_files} (40–80: {'ĐẠT' if summary['target_40_80_files'] else 'HỎNG'})  "
        f"ảnh={rep.n_images}  bảng rộng(≥4 cột)={n_wide_tables}"
    )
    print(
        f"dòng: vision={hybrid.vision_lines} assigned={hybrid.assigned_lines} "
        f"floating={hybrid.floating_lines} furniture={hybrid.furniture_lines}"
    )
    print(
        f"bất biến A={'ĐẠT' if inv_a_ok else f'HỎNG ({outside})'} | "
        f"B(a+f+furniture=cache)={'ĐẠT' if inv_b_ok else 'HỎNG'}"
    )
    print(
        f"SỐ ĐẾM còn sót: tiêu đề chạy={running_header_leak}  mục lục in sẵn={toc_leak}  "
        f"»={char_counts_strange['»']} ®={char_counts_strange['®']} _={char_counts_strange['_']} "
        f"•={char_counts_strange['•']}"
    )
    print(
        f"ký tự EPUB {final_nonspace} ≤ cache {cache_nonspace}: "
        f"{'ĐẠT' if final_nonspace <= cache_nonspace else 'HỎNG'}"
    )
    print(f"tất định={deterministic} | epubcheck: {epubcheck}")
    print(f"→ {a} + {OUT}/summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
