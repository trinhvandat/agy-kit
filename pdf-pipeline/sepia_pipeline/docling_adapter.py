"""Adapter Docling → **mô hình trung gian** (Mốc 1b, cho sách ``scan_ocr``).

Chuyển kết quả Docling về đúng ``Block`` (Heading/Paragraph/Table/ImageBlock) mà :mod:`build_epub`
dùng — **không** có đường dựng EPUB thứ hai. Docling chạy **dùng lớp chữ sẵn trong PDF** (không OCR
lại). Optional extra (``uv sync --extra docling``); thiếu thì :func:`docling_available` trả False.
"""

from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path

from .model import Block, Heading, ImageBlock, Paragraph, Table
from .reflow import normalize_text

# Nhãn Docling → vai trò.
_HEADING_LABELS = {"section_header", "title"}
_PARA_LABELS = {"text", "paragraph", "list_item", "footnote", "code", "formula"}
_SKIP_LABELS = {"page_header", "page_footer"}  # running head — Docling tự tách, ta bỏ


def docling_available() -> bool:
    """True nếu đã cài extra ``docling``."""
    return importlib.util.find_spec("docling") is not None


INSTALL_HINT = "Docling chưa cài. Cài bằng: `uv sync --extra docling` (nặng: torch/transformers)."


def _label(item) -> str:
    label = getattr(item, "label", "")
    return getattr(label, "value", str(label))


def _page_no(item) -> int:
    prov = getattr(item, "prov", None)
    if prov:
        return int(getattr(prov[0], "page_no", 0) or 0)
    return 0


def _png_of(item, doc) -> bytes | None:
    try:
        img = item.get_image(doc)
    except Exception:
        img = None
    if img is None:
        return None
    buf = BytesIO()
    img.save(buf, format="PNG")  # PIL PNG không nhúng thời gian → tất định
    return buf.getvalue()


def _table_rows(item) -> tuple[tuple[str, ...], ...]:
    data = getattr(item, "data", None)
    grid = getattr(data, "grid", None)
    if not grid:
        return ()
    rows = []
    for row in grid:
        rows.append(tuple(normalize_text(getattr(c, "text", "") or "") for c in row))
    return tuple(rows)


def _caption_text(item, doc) -> str:
    try:
        return normalize_text(item.caption_text(doc) or "")
    except Exception:
        return ""


def _build_converter(image_scale: float):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = False  # dùng lớp chữ sẵn trong PDF (scan_ocr), KHÔNG OCR lại
    opts.generate_picture_images = True
    opts.images_scale = image_scale
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )


def extract_blocks_docling(pdf_path: str | Path, *, image_scale: float = 2.0) -> list[Block]:
    """Trích ``pdf_path`` bằng Docling → danh sách ``Block`` theo thứ tự đọc.

    Cần đã cài extra docling (xem :func:`docling_available`).
    """
    conv = _build_converter(image_scale)
    doc = conv.convert(str(pdf_path)).document

    blocks: list[Block] = []
    for item, _level in doc.iterate_items():
        label = _label(item)
        if label in _SKIP_LABELS:
            continue
        page = _page_no(item)

        if label in _HEADING_LABELS:
            text = normalize_text(getattr(item, "text", "") or "")
            if not text:
                continue
            level = 1 if label == "title" else max(1, min(3, int(getattr(item, "level", 2) or 2)))
            blocks.append(Heading(text=text, level=level, page=page))
        elif label == "picture":
            png = _png_of(item, doc)
            if png is not None:
                blocks.append(ImageBlock(png=png, page=page, caption=_caption_text(item, doc)))
        elif label == "table":
            rows = _table_rows(item)
            if rows:
                blocks.append(Table(rows=rows, page=page))
        elif label == "caption":
            # Gắn chú thích vào ảnh ngay trước (nếu có).
            text = normalize_text(getattr(item, "text", "") or "")
            if text and blocks and isinstance(blocks[-1], ImageBlock) and not blocks[-1].caption:
                prev = blocks[-1]
                blocks[-1] = ImageBlock(png=prev.png, page=prev.page, caption=text)
            elif text:
                blocks.append(Paragraph(text=text, page=page))
        elif label in _PARA_LABELS:
            text = normalize_text(getattr(item, "text", "") or "")
            if not text:
                continue
            if label == "list_item":
                text = f"• {text}"
            blocks.append(Paragraph(text=text, page=page))
    return blocks
