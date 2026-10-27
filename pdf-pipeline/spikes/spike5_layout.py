"""SPIKE-5 (bố cục) — Docling + **Apple Vision OCR** (OcrMacOptions) trong MỘT bước.

Mục tiêu (xem docs/spikes/spike-5-reocr-vision.md, mục "Tích hợp"): kiểm cách GỌN nhất — để
Docling vừa dựng **bố cục** (reading-order nhiều cột, cắt hình, heading) vừa lấy **chữ** từ ảnh
bằng **Apple Vision** (`force_full_page_ocr=True`, `framework="vision"`, `recognition="accurate"`,
`lang=["vi-VT"]`). Docling 2.142 CÓ sẵn engine này ⇒ không cần tự "thay chữ theo dòng".

So 3 hướng trên cùng tập trang:
  - hidden   : Docling đọc **lớp chữ ẩn ABBYY** (do_ocr=False) — bố cục Docling, chữ ABBYY.
  - vision_raw: Apple Vision OCR thẳng từ ảnh (spikes/fixtures) — chữ Vision, KHÔNG bố cục.
  - docling_vision: Docling + Apple Vision — **bố cục Docling + chữ Vision**.

Đo: CER/WER (trên 3 trang có ground truth), **độ phủ chữ** so lớp ẩn, **thứ tự đọc** p23
(nhiều cột), **giữ hình + chú thích** p101, **thời gian/trang**.

    cd pdf-pipeline
    uv sync --extra docling
    uv run --with rapidfuzz --with ocrmac python spikes/spike5_layout.py "../samples/<tên>.pdf"

CHỈ chạy trên macOS (Apple Vision). Xuất ra out/spike5_layout/.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pymupdf as fitz

# dùng lại bộ chấm CER/WER của spike5_cer_wer.py (cùng thư mục)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from spike5_cer_wer import GT_DIR, Levenshtein, match_window, norm, parse_gt  # noqa: E402

GT_PAGES = [23, 101, 186]
SAMPLE_PAGES = [25, 55, 85, 115, 145, 175, 205, 235, 265, 280]
PAGES = GT_PAGES + SAMPLE_PAGES
OUT = Path("out/spike5_layout")


def subset(src: Path, pages: list[int], dst: Path) -> list[int]:
    doc = fitz.open(str(src))
    keep = [p for p in pages if p < doc.page_count]
    doc.select(keep)
    doc.save(str(dst))
    doc.close()
    return keep


def hidden_text_by_page(src: Path, pages: list[int]) -> dict[int, str]:
    doc = fitz.open(str(src))
    out = {p: doc[p].get_text("text") for p in pages}
    doc.close()
    return out


def docling_vision(subset_pdf: Path):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import OcrMacOptions, PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = True
    opts.generate_picture_images = True
    opts.ocr_options = OcrMacOptions(
        force_full_page_ocr=True,
        lang=["vi-VT"],
        recognition="accurate",
        framework="vision",
    )
    conv = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )
    t0 = time.time()
    res = conv.convert(str(subset_pdf))
    return res, time.time() - t0


def page_texts(doc) -> dict[int, list[str]]:
    """Văn bản theo thứ tự đọc Docling, gom theo số trang (1-based trong subset)."""
    by_page: dict[int, list[str]] = {}
    for item in doc.texts:
        if not getattr(item, "prov", None):
            continue
        pno = item.prov[0].page_no
        by_page.setdefault(pno, []).append(item.text)
    return by_page


def pictures_per_page(doc) -> dict[int, int]:
    counts: dict[int, int] = {}
    for pic in doc.pictures:
        if getattr(pic, "prov", None):
            pno = pic.prov[0].page_no
            counts[pno] = counts.get(pno, 0) + 1
    return counts


def cer_wer(gt_blocks: list[dict], ocr_norm: str):
    ec = gc = ew = gw = 0
    for b in gt_blocks:
        gt_t = b["text"]
        gt_w = gt_t.split()
        hyp_t = match_window(gt_t, ocr_norm)
        ec += Levenshtein.distance(gt_t, hyp_t)
        gc += len(gt_t)
        ew += Levenshtein.distance(gt_w, hyp_t.split())
        gw += len(gt_w)
    return (
        round(ec / gc * 100, 2) if gc else None,
        round(ew / gw * 100, 2) if gw else None,
    )


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if src is None or not src.exists():
        print("Dùng: spike5_layout.py <đường dẫn .pdf>  (../samples/<tên>.pdf)")
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    sub = OUT / "subset.pdf"
    keep = subset(src, PAGES, sub)
    print(f"Trang (0-based gốc): {keep}")
    hidden = hidden_text_by_page(src, keep)

    res, dt = docling_vision(sub)
    doc = res.document
    by_page = page_texts(doc)
    pics = pictures_per_page(doc)

    rows = []
    for i, orig in enumerate(keep):
        pno = i + 1  # Docling 1-based trong subset
        dv_text = "\n".join(by_page.get(pno, []))
        (OUT / f"p{orig:04d}_docling_vision.txt").write_text(dv_text, encoding="utf-8")
        hid = hidden.get(orig, "")
        row = {
            "page": orig,
            "docling_vision_chars": len(dv_text),
            "hidden_chars": len(hid),
            "coverage_vs_hidden_pct": round(len(dv_text) / len(hid) * 100, 1) if hid else None,
            "pictures": pics.get(pno, 0),
        }
        if orig in GT_PAGES:
            gt = parse_gt(GT_DIR / f"p{orig:04d}.txt")
            cer, wer = cer_wer(gt, norm(dv_text))
            row["cer_pct"], row["wer_pct"] = cer, wer
        rows.append(row)

    summary = {
        "engine": "docling+apple-vision (OcrMacOptions, vi-VT, full_page, accurate)",
        "docling": __import__("docling").__version__,
        "pages": keep,
        "seconds_total": round(dt, 2),
        "seconds_per_page": round(dt / len(keep), 2),
        "total_pictures": sum(pics.values()),
        "per_page": rows,
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        f"\nDocling+Vision: {summary['seconds_total']}s "
        f"({summary['seconds_per_page']}s/trang) | {summary['total_pictures']} hình\n"
    )
    print(f"{'page':>5} {'cov%':>6} {'pics':>5} {'CER':>7} {'WER':>7}")
    for r in rows:
        cer = f"{r.get('cer_pct')}" if r.get("cer_pct") is not None else "—"
        wer = f"{r.get('wer_pct')}" if r.get("wer_pct") is not None else "—"
        cov = r["coverage_vs_hidden_pct"]
        print(f"{r['page']:>5} {cov!s:>6} {r['pictures']:>5} {cer:>7} {wer:>7}")

    # Thứ tự đọc p23 (nhiều cột): 150 ký tự đầu nên là đoạn mở đầu "Lịch sử phát triển..."
    p23 = "\n".join(by_page.get(keep.index(23) + 1, []))
    print("\n[p23 reading-order] 160 ký tự đầu Docling+Vision:")
    print("  " + " ".join(p23.split())[:160])
    print("\n→ out/spike5_layout/summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
