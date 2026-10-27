"""SPIKE-5 (đo v5 → v5.1 / PIPELINE_VERSION 6) — vá rò lớp chữ ABBYY ở route hybrid.

Một lần convert Docling, đo trên CẢ CUỐN:
- BẤT BIẾN: (A) mọi từ khối chữ trên trang CÓ cache ⊆ chữ cache trang đó; (B) mỗi dòng cache dùng
  đúng một lần (assigned + floating == vision_lines == cache.n_lines).
- "Chữ ngoài nguồn": số từ trong EPUB (khối chữ cuối cùng) không có trong cache Vision (≈ 0).
- Tổng ký tự EPUB (không trắng) ≤ tổng ký tự cache.
- Token lỗi ABBYY (nhiéu/điéu/vđi/Phưdng/xưong/cùa) trong EPUB vs trong cache → phải về mức cache.
- CER/WER 3 trang GT: (cũ) cửa sổ khớp nhất + (mới) toàn trang theo thứ tự output (tính CẢ chèn).
- Dòng trôi %: nếu > 5% → in chẩn đoán (phân bố overlap lớn nhất, nhãn khối gần nhất).
- Tất định (build 2 lần từ cùng blocks) + epubcheck.

    cd pdf-pipeline
    uv run --with rapidfuzz python spikes/spike5_v51_measure.py "../samples/<tên>.pdf"
"""

from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import pymupdf as fitz

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spike5_cer_wer import GT_DIR, Levenshtein, match_window, norm, parse_gt  # noqa: E402

from sepia_pipeline import PIPELINE_VERSION  # noqa: E402
from sepia_pipeline.build_epub import build_epub  # noqa: E402
from sepia_pipeline.detect import DetectConfig  # noqa: E402
from sepia_pipeline.extract import extract_document, sha256_file  # noqa: E402
from sepia_pipeline.model import Heading, ImageBlock, Paragraph, Table  # noqa: E402
from sepia_pipeline.ocr_cache import DEFAULT_CACHE_DIR, read_cache  # noqa: E402
from sepia_pipeline.ocr_hybrid import (  # noqa: E402
    _assemble_blocks,
    _assign_lines,
    _build_converter,
    _build_targets,
    _center_dist2,
    _insert_floating,
    _overlap_frac,
)
from sepia_pipeline.quality import run_epubcheck  # noqa: E402
from sepia_pipeline.reflow import drop_garbage_blocks, drop_printed_toc  # noqa: E402
from sepia_pipeline.vietnamese import looks_vietnamese  # noqa: E402

GT_PAGES = [23, 101, 186]
OUT = Path("out/spike5_v51")
ABBYY_TOKENS = ["nhiéu", "điéu", "vđi", "Phưdng", "xưong", "cùa"]
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def _toks(text: str) -> list[str]:
    return [t.casefold() for t in _WORD.findall(unicodedata.normalize("NFC", text))]


def _nonspace(text: str) -> int:
    return sum(1 for ch in text if not ch.isspace())


def _count_tokens(text: str) -> dict[str, int]:
    low = unicodedata.normalize("NFC", text)
    return {tok: len(re.findall(re.escape(tok), low)) for tok in ABBYY_TOKENS}


def _post(blocks):
    """Hậu xử lý như convert (nguồn OCR + tiếng Việt): lọc rác âm tiết + bỏ mục lục in sẵn."""
    book_text = " ".join(b.text for b in blocks if isinstance(b, Heading | Paragraph))
    removed = 0
    if looks_vietnamese(book_text):
        g = drop_garbage_blocks(blocks)
        blocks, removed = g.kept, len(g.removed)
    blocks, toc = drop_printed_toc(blocks)
    return blocks, removed, toc


def _page_text(blocks, page0: int) -> str:
    return " ".join(
        b.text
        for b in blocks
        if getattr(b, "page", 0) == page0 + 1 and isinstance(b, Heading | Paragraph)
    )


def _cer_wer_window(blocks, page0: int):
    """CŨ: ghép mỗi khối GT với cửa sổ khớp nhất trong text trang (không phạt chèn thừa)."""
    txt = norm(_page_text(blocks, page0))
    ec = gc = ew = gw = 0
    for b in parse_gt(GT_DIR / f"p{page0:04d}.txt"):
        h = match_window(b["text"], txt)
        ec += Levenshtein.distance(b["text"], h)
        gc += len(b["text"])
        ew += Levenshtein.distance(b["text"].split(), h.split())
        gw += len(b["text"].split())
    return (round(ec / gc * 100, 2) if gc else None, round(ew / gw * 100, 2) if gw else None)


def _cer_wer_fullpage(blocks, page0: int):
    """MỚI: GT (nối theo thứ tự GT) ↔ TOÀN BỘ text trang (thứ tự output) → tính CẢ chèn/đổi chỗ."""
    hyp = norm(_page_text(blocks, page0))
    ref = norm(" ".join(b["text"] for b in parse_gt(GT_DIR / f"p{page0:04d}.txt")))
    rw, hw = ref.split(), hyp.split()
    cer = round(Levenshtein.distance(ref, hyp) / len(ref) * 100, 2) if ref else None
    wer = round(Levenshtein.distance(rw, hw) / len(rw) * 100, 2) if rw else None
    return cer, wer, len(rw), len(hw)


def _floating_diag(targets, lines_by_page, floating_by_page) -> dict:
    """Vì sao dòng trôi nhiều? Phân bố overlap LỚN NHẤT của mỗi dòng trôi với khối cùng trang."""
    by_page: dict[int, list] = {}
    for t in targets:
        by_page.setdefault(t.page, []).append(t)
    buckets = {"0 (không khối nào)": 0, "0–0.1": 0, "0.1–0.2 (gần ngưỡng)": 0}
    near_label: dict[str, int] = {}
    pages_no_target = 0
    for page, lines in floating_by_page.items():
        tgts = by_page.get(page, [])
        if not tgts:
            pages_no_target += 1
        for ln in lines:
            best = max((_overlap_frac(ln.bbox, t.bbox) for t in tgts), default=0.0)
            if best <= 0.0:
                buckets["0 (không khối nào)"] += 1
            elif best < 0.1:
                buckets["0–0.1"] += 1
            else:
                buckets["0.1–0.2 (gần ngưỡng)"] += 1
            if tgts:
                nearest = min(tgts, key=lambda t: _center_dist2(ln.bbox, t.bbox))
                near_label[nearest.label] = near_label.get(nearest.label, 0) + 1
    return {
        "overlap_buckets": buckets,
        "nearest_block_label": dict(sorted(near_label.items(), key=lambda x: -x[1])),
        "floating_on_pages_with_no_target": pages_no_target,
    }


def main() -> int:
    pdf = Path(sys.argv[1])
    OUT.mkdir(parents=True, exist_ok=True)
    cache = read_cache(DEFAULT_CACHE_DIR, sha256_file(pdf))
    assert cache is not None, "chưa có cache — chạy `sepia-pipeline ocr` trước"
    cache_words = {p.page: set(_toks(" ".join(ln.text for ln in p.lines))) for p in cache.pages}
    cache_nonspace = sum(_nonspace(ln.text) for p in cache.pages for ln in p.lines)
    cache_token_counts = _count_tokens(" ".join(ln.text for p in cache.pages for ln in p.lines))

    fdoc = fitz.open(str(pdf))
    doc_model = extract_document(fdoc, pdf, DetectConfig())
    fdoc.close()

    # --- MỘT lần convert Docling, chạy từng bước để lấy cả chẩn đoán dòng trôi ---
    t0 = time.time()
    conv = _build_converter(2.0)
    doc = conv.convert(str(pdf)).document
    order_items, targets = _build_targets(doc)
    lines_by_page = {p.page: list(p.lines) for p in cache.pages}
    assigned, cross, floating_by_page = _assign_lines(targets, lines_by_page)
    cached_pages = set(lines_by_page)
    diag = _floating_diag(targets, lines_by_page, floating_by_page)
    order_items2, floating = _insert_floating(order_items, floating_by_page)
    blocks_raw, dropped = _assemble_blocks(order_items2, doc, cached_pages)
    t_extract = round(time.time() - t0, 1)

    vision_lines = sum(len(v) for v in lines_by_page.values())
    blocks, garbage, toc = _post(list(blocks_raw))

    # --- BẤT BIẾN ---
    inv_b_ok = assigned + floating == vision_lines == cache.n_lines
    outside = []  # (page, word, block_text[:60])
    for b in blocks:
        if not isinstance(b, Heading | Paragraph):
            continue
        p0 = getattr(b, "page", 0) - 1
        if p0 not in cache_words:
            continue
        for w in _toks(b.text):
            if w not in cache_words[p0]:
                outside.append({"page": p0, "word": w, "block": b.text[:60]})
    inv_a_ok = len(outside) == 0
    # Chữ ngoài nguồn từ bảng (ABBYY) — đo riêng (route hybrid chưa thay chữ bảng bằng Vision).
    table_outside = 0
    for b in blocks:
        if isinstance(b, Table):
            p0 = getattr(b, "page", 0) - 1
            txt = " ".join(c for row in b.rows for c in row)
            table_outside += sum(1 for w in _toks(txt) if w not in cache_words.get(p0, set()))

    final_nonspace = _nonspace(" ".join(b.text for b in blocks if hasattr(b, "text")))
    final_token_counts = _count_tokens(" ".join(b.text for b in blocks if hasattr(b, "text")))

    cer_wer = {}
    for p in GT_PAGES:
        cw_old = _cer_wer_window(blocks, p)
        cer_n, wer_n, gw, hw = _cer_wer_fullpage(blocks, p)
        cer_wer[p] = {
            "window_cer_wer": cw_old,
            "fullpage_cer": cer_n,
            "fullpage_wer": wer_n,
            "gt_words": gw,
            "out_words": hw,
        }

    # --- EPUB v6 + tất định + epubcheck ---
    a, b_ = OUT / "v51_a.epub", OUT / "v51_b.epub"
    build_epub(doc_model, blocks, a, pipeline_version=PIPELINE_VERSION)
    build_epub(doc_model, blocks, b_, pipeline_version=PIPELINE_VERSION)
    deterministic = a.read_bytes() == b_.read_bytes()
    epubcheck = run_epubcheck(str(a))

    for p in GT_PAGES:
        (OUT / f"p{p:04d}_v6.txt").write_text(
            "\n".join(
                b.text for b in blocks if getattr(b, "page", 0) == p + 1 and hasattr(b, "text")
            ),
            encoding="utf-8",
        )

    floating_pct = round(100.0 * floating / vision_lines, 2) if vision_lines else 0.0
    summary = {
        "pipeline_version": PIPELINE_VERSION,
        "extract_sec": t_extract,
        "deterministic_build": deterministic,
        "epubcheck": epubcheck,
        "counts": {
            "headings": sum(1 for b in blocks if isinstance(b, Heading)),
            "paragraphs": sum(1 for b in blocks if isinstance(b, Paragraph)),
            "images": sum(1 for b in blocks if isinstance(b, ImageBlock)),
            "tables": sum(1 for b in blocks if isinstance(b, Table)),
            "garbage_removed": garbage,
            "toc_removed": toc,
        },
        "hybrid": {
            "vision_lines": vision_lines,
            "cache_n_lines": cache.n_lines,
            "assigned": assigned,
            "cross_block": cross,
            "floating": floating,
            "floating_pct": floating_pct,
            "dropped_empty_blocks": dropped,
            "fallback_pages": len([p0 for p0 in range(len(cache.pages)) if p0 not in cached_pages]),
        },
        "invariants": {
            "A_cached_words_subset_cache": inv_a_ok,
            "B_each_line_used_once": inv_b_ok,
            "outside_source_words": len(outside),
            "outside_source_examples": outside[:20],
            "table_outside_source_words": table_outside,
        },
        "chars": {
            "final_nonspace": final_nonspace,
            "cache_nonspace": cache_nonspace,
            "final_le_cache": final_nonspace <= cache_nonspace,
        },
        "abbyy_tokens": {"final": final_token_counts, "cache": cache_token_counts},
        "cer_wer_gt": cer_wer,
        "floating_diag": diag,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")

    # ---- in bảng ----
    print(
        f"\nPIPELINE_VERSION={PIPELINE_VERSION} | extract={t_extract}s | tất định={deterministic}"
    )
    print(f"epubcheck: {epubcheck}\n")
    h = summary["hybrid"]
    print(
        f"vision_lines={h['vision_lines']} assigned={h['assigned']} cross={h['cross_block']} "
        f"floating={h['floating']} ({h['floating_pct']}%) dropped={h['dropped_empty_blocks']} "
        f"fallback_pages={h['fallback_pages']}"
    )
    print(
        f"\nBẤT BIẾN A (từ khối ⊆ cache): {'ĐẠT' if inv_a_ok else 'HỎNG'} "
        f"— chữ ngoài nguồn={len(outside)} (bảng ABBYY riêng={table_outside})"
    )
    print(
        f"BẤT BIẾN B (mỗi dòng 1 lần): {'ĐẠT' if inv_b_ok else 'HỎNG'} "
        f"— assigned+floating={assigned + floating} vs cache={cache.n_lines}"
    )
    print(
        f"\nKý tự (không trắng): EPUB={final_nonspace} ≤ cache={cache_nonspace}? "
        f"{'ĐẠT' if final_nonspace <= cache_nonspace else 'HỎNG'}"
    )
    print("\nToken lỗi ABBYY (EPUB vs cache):")
    for tok in ABBYY_TOKENS:
        print(f"  {tok:8}: EPUB={final_token_counts[tok]:>4}  cache={cache_token_counts[tok]:>4}")
    print("\nCER/WER 3 trang GT:")
    for p in GT_PAGES:
        r = cer_wer[p]
        print(
            f"  p{p}: cửa sổ(CER,WER)={r['window_cer_wer']}  toàn-trang WER(tính chèn)="
            f"{r['fullpage_wer']}%  (GT {r['gt_words']} từ → output {r['out_words']} từ)"
        )
    if floating_pct > 5.0:
        print(f"\n⚠ Dòng trôi {floating_pct}% > 5% — CHẨN ĐOÁN:")
        print(f"  overlap lớn nhất: {diag['overlap_buckets']}")
        print(f"  nhãn khối gần nhất: {diag['nearest_block_label']}")
        print(
            f"  dòng trôi trên trang KHÔNG có khối nào: {diag['floating_on_pages_with_no_target']}"
        )
    print("\n→ out/spike5_v51/summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
