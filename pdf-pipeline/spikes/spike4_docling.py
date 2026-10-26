"""SPIKE-4 — so sánh pipeline hiện tại vs **Docling** trên vài trang đại diện của sách mẫu.

Thử nghiệm, **chưa** thay pipeline (xem docs/spikes/spike-4-docling.md). Cần cài extra docling:

    uv sync --extra docling
    uv run python spikes/spike4_docling.py "../samples/<tên>.pdf"

Xuất ra ``pdf-pipeline/out/spike4/``:
- ``current.md``  — văn bản theo pipeline hiện tại (heuristic),
- ``docling.md``  — Markdown của Docling (lớp chữ có sẵn, không OCR; fallback OCR vie nếu rỗng),
- ``docling_pic_*.png`` — hình Docling cắt được,
- ``summary.json`` — thời gian chạy/trang, số hình, có dùng OCR không.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pymupdf as fitz

from sepia_pipeline.detect import DetectConfig
from sepia_pipeline.extract import extract_document
from sepia_pipeline.model import Heading, ImageBlock, Paragraph
from sepia_pipeline.reflow import build_blocks

# Trang đại diện (0-based): bìa scan, mục lục, trang nhiều cột/sidebar, trang có hình + heading to,
# vài trang thân bài, phụ bản cuối.
REPRESENTATIVE_PAGES = [0, 10, 30, 60, 99, 149, 199, 230, 260, 289]
OUT = Path("out/spike4")


def make_subset(src: Path, pages: list[int], dst: Path) -> int:
    doc = fitz.open(str(src))
    keep = [p for p in pages if p < doc.page_count]
    doc.select(keep)
    doc.save(str(dst))
    n = doc.page_count
    doc.close()
    return n


def current_markdown(subset_pdf: Path) -> str:
    doc_fitz = fitz.open(str(subset_pdf))
    doc = extract_document(doc_fitz, subset_pdf, DetectConfig())
    doc_fitz.close()
    out: list[str] = []
    for b in build_blocks(doc):
        if isinstance(b, Heading):
            out.append(f"{'#' * min(b.level, 3)} {b.text}")
        elif isinstance(b, Paragraph):
            out.append(b.text)
        elif isinstance(b, ImageBlock):
            out.append(f"![trang {b.page}] (ảnh render nguyên trang)")
    return "\n\n".join(out)


def _converter(do_ocr: bool, ocr_lang: list[str] | None = None):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = do_ocr
    opts.generate_picture_images = True
    if do_ocr and ocr_lang:
        try:
            opts.ocr_options.lang = ocr_lang
        except Exception:
            pass
    fmt = {InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    return DocumentConverter(format_options=fmt)


def docling_run(subset_pdf: Path, n_pages: int) -> dict:
    result: dict = {"ocr_used": False}
    conv = _converter(do_ocr=False)
    t0 = time.time()
    res = conv.convert(str(subset_pdf))
    dt = time.time() - t0
    md = res.document.export_to_markdown()

    # Nếu lớp chữ không dùng được (markdown gần rỗng) → thử OCR tiếng Việt.
    if len(md.strip()) < 200:
        try:
            conv2 = _converter(do_ocr=True, ocr_lang=["vi"])
            t0 = time.time()
            res = conv2.convert(str(subset_pdf))
            dt = time.time() - t0
            md = res.document.export_to_markdown()
            result["ocr_used"] = True
        except Exception as exc:  # noqa: BLE001 - spike, chỉ ghi lại
            result["ocr_error"] = f"{type(exc).__name__}: {exc}"

    pics: list[str] = []
    try:
        for i, pic in enumerate(res.document.pictures):
            img = pic.get_image(res.document)
            if img is not None:
                name = f"docling_pic_{i:02d}.png"
                img.save(OUT / name)
                pics.append(name)
    except Exception as exc:  # noqa: BLE001
        result["picture_error"] = f"{type(exc).__name__}: {exc}"

    result.update(
        markdown=md,
        seconds=round(dt, 2),
        seconds_per_page=round(dt / n_pages, 2) if n_pages else None,
        n_pictures=len(pics),
        pictures=pics,
    )
    return result


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if src is None or not src.exists():
        print("Dùng: spike4_docling.py <đường dẫn .pdf>  (thường là ../samples/<tên>.pdf)")
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    subset = OUT / "subset_pages.pdf"
    n = make_subset(src, REPRESENTATIVE_PAGES, subset)
    print(f"Trang đại diện: {REPRESENTATIVE_PAGES[:n]} ({n} trang)")

    cur = current_markdown(subset)
    (OUT / "current.md").write_text(cur, encoding="utf-8")
    print(f"current.md: {len(cur)} ký tự")

    doc = docling_run(subset, n)
    (OUT / "docling.md").write_text(doc.pop("markdown"), encoding="utf-8")
    (OUT / "summary.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"docling.md: ocr={doc['ocr_used']} | {doc['seconds']}s "
        f"({doc['seconds_per_page']}s/trang) | {doc['n_pictures']} hình"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
