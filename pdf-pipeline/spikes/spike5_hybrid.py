"""SPIKE-5 (bố cục, hướng 2) — **Docling layout + chữ Apple Vision theo toạ độ**.

Vì sao: hướng GỌN (Docling + OcrMacOptions, xem spike5_layout.py) CHẠY ĐƯỢC nhưng chữ **tệ hơn
~10×** so với Vision chạy thẳng trên ảnh render (WER p101 ~20% vs ~2%) — lỗi nằm trong **khâu OCR
nội bộ của Docling**, không phải Vision/ocrmac/renderer (ocrmac trên ảnh PyMuPDF/pypdfium2
đều ~2% WER). ⇒ Làm hướng 2 (brief): **giữ bố cục Docling, thay chữ bằng Vision theo toạ độ dòng**.

Cách làm (một lần OCR cả trang, giữ nguyên chất lượng Vision):
  1. Docling(do_ocr=False) → **khối + bbox + thứ tự đọc** (bố cục; chữ ABBYY bỏ đi).
  2. Render trang 300 DPI (PyMuPDF) → **Apple Vision OCR cả trang** (ocrmac) → **dòng + bbox**.
  3. Gán mỗi dòng Vision vào khối Docling **chứa tâm dòng** (chuẩn hoá bbox, gốc dưới-trái);
     xuất theo **thứ tự khối của Docling**, trong khối sắp dòng trên→dưới.

Đo: CER/WER (3 trang GT), thứ tự đọc p23, giữ hình, thời gian. CHỈ chạy macOS.

    uv sync --extra docling
    uv run --with rapidfuzz --with ocrmac python spikes/spike5_hybrid.py "../samples/<tên>.pdf"
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import ocrmac.ocrmac as oc
import pymupdf as fitz

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spike5_cer_wer import GT_DIR, Levenshtein, match_window, norm, parse_gt  # noqa: E402

GT_PAGES = [23, 101, 186]
OUT = Path("out/spike5_hybrid")


def docling_layout(subset_pdf: Path):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = False  # chỉ lấy BỐ CỤC; chữ sẽ thay bằng Vision
    opts.generate_picture_images = True
    conv = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )
    return conv.convert(subset_pdf).document


def docling_blocks(doc, pno: int):
    """Khối text của Docling trên trang pno (1-based), kèm bbox chuẩn hoá (gốc dưới-trái)."""
    page = doc.pages[pno]
    w, h = page.size.width, page.size.height
    blocks = []
    for it in doc.texts:
        if not it.prov or it.prov[0].page_no != pno:
            continue
        bb = it.prov[0].bbox.to_bottom_left_origin(h)
        blocks.append(
            {
                "order": len(blocks),
                "lx": bb.l / w,
                "rx": bb.r / w,
                "by": min(bb.t, bb.b) / h,
                "ty": max(bb.t, bb.b) / h,
                "lines": [],
            }
        )
    return blocks


def vision_lines(pdf: Path, page0: int, dpi: int = 300):
    """Apple Vision OCR cả trang → [(text, cx, cy)] chuẩn hoá (gốc dưới-trái)."""
    doc = fitz.open(str(pdf))
    img = OUT / f"p{page0:04d}.png"
    doc[page0].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72)).save(str(img))
    doc.close()
    out = []
    for text, _conf, (x, y, w, h) in oc.OCR(
        str(img), framework="vision", recognition_level="accurate", language_preference=["vi-VT"]
    ).recognize():
        out.append((text, x + w / 2, y + h / 2))
    return out


def assign(blocks, lines):
    """Gán mỗi dòng Vision vào khối Docling chứa tâm; nếu không khối nào chứa → khối gần nhất."""
    for text, cx, cy in lines:
        hits = [b for b in blocks if b["lx"] <= cx <= b["rx"] and b["by"] <= cy <= b["ty"]]
        if hits:
            tgt = min(
                hits, key=lambda b: (b["rx"] - b["lx"]) * (b["ty"] - b["by"])
            )  # khối nhỏ nhất
        elif blocks:
            tgt = min(
                blocks,
                key=lambda b: (
                    (cx - (b["lx"] + b["rx"]) / 2) ** 2 + (cy - (b["by"] + b["ty"]) / 2) ** 2
                ),
            )
        else:
            continue
        tgt["lines"].append((cy, cx, text))
    out = []
    for b in blocks:
        b["lines"].sort(key=lambda t: (-t[0], t[1]))  # trên→dưới, trái→phải
        if b["lines"]:
            out.append(" ".join(t[2] for t in b["lines"]))
    return out


def cer_wer(gt_blocks, ocr_norm):
    ec = gc = ew = gw = 0
    for b in gt_blocks:
        gt_t = b["text"]
        h = match_window(gt_t, ocr_norm)
        ec += Levenshtein.distance(gt_t, h)
        gc += len(gt_t)
        ew += Levenshtein.distance(gt_t.split(), h.split())
        gw += len(gt_t.split())
    return (round(ec / gc * 100, 2) if gc else None, round(ew / gw * 100, 2) if gw else None)


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if src is None or not src.exists():
        print("Dùng: spike5_hybrid.py <đường dẫn .pdf>")
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    d = fitz.open(str(src))
    d.select(GT_PAGES)
    sub = OUT / "subset.pdf"
    d.save(str(sub))
    d.close()

    t0 = time.time()
    doc = docling_layout(sub)
    pics = {}
    for pic in doc.pictures:
        if pic.prov:
            pics[pic.prov[0].page_no] = pics.get(pic.prov[0].page_no, 0) + 1

    rows = []
    for i, page0 in enumerate(GT_PAGES):
        pno = i + 1
        blocks = docling_blocks(doc, pno)
        lines = vision_lines(src, page0)
        ordered = assign(blocks, lines)
        text = "\n".join(ordered)
        (OUT / f"p{page0:04d}_hybrid.txt").write_text(text, encoding="utf-8")
        gt = parse_gt(GT_DIR / f"p{page0:04d}.txt")
        cer, wer = cer_wer(gt, norm(text))
        rows.append(
            {
                "page": page0,
                "blocks": len(blocks),
                "pictures": pics.get(pno, 0),
                "cer_pct": cer,
                "wer_pct": wer,
                "first": " ".join(text.split())[:90],
            }
        )
    dt = time.time() - t0

    summary = {
        "engine": "docling-layout + apple-vision-by-bbox",
        "pages": GT_PAGES,
        "seconds_total": round(dt, 2),
        "per_page": rows,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")
    print(f"Docling-layout + Vision-theo-bbox | {round(dt, 1)}s\n")
    print(f"{'page':>5} {'blk':>4} {'pics':>5} {'CER':>7} {'WER':>7}  reading-order đầu khối")
    for r in rows:
        print(
            f"{r['page']:>5} {r['blocks']:>4} {r['pictures']:>5} "
            f"{r['cer_pct']!s:>7} {r['wer_pct']!s:>7}  {r['first'][:60]}"
        )
    print("\n→ out/spike5_hybrid/summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
