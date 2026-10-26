"""Bước 1 — Trích chữ **theo span** bằng PyMuPDF ``get_text("dict")`` (ADR-004).

Lớp mỏng bọc PyMuPDF: dựng mô hình trung gian (:mod:`model`) từ PDF, giữ bbox/font/cỡ/kiểu/số
trang. Chuyển mã font cũ **ngay tại đây, theo từng span** (sau khi trích — ADR-005) nên các bước
sau chỉ thấy Unicode sạch. Thứ tự đọc: theo thứ tự block của PyMuPDF (``sort=True``); nhiều cột
chưa xử lý (chỉ phát hiện + cảnh báo ở :mod:`reflow`).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pymupdf as fitz

from .detect import DetectConfig, _page_image_coverage
from .legacy_encoding import convert_span_text
from .model import Document, Line, Page, TextSpan

# Bit cờ trong span["flags"] của PyMuPDF.
_FLAG_ITALIC = 1 << 1  # 2
_FLAG_BOLD = 1 << 4  # 16


def sha256_file(path: str | Path, *, chunk: int = 1 << 20) -> str:
    """SHA-256 của **file PDF gốc** (đọc theo khối, không nạp cả file vào RAM)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _is_bold(font: str, flags: int) -> bool:
    return bool(flags & _FLAG_BOLD) or "bold" in font.lower()


def _is_italic(font: str, flags: int) -> bool:
    name = font.lower()
    return bool(flags & _FLAG_ITALIC) or "italic" in name or "oblique" in name


def _extract_line(line_dict: dict, page_number: int, config: DetectConfig) -> Line | None:
    """Dựng một :class:`Line` từ dict của PyMuPDF; chuyển mã legacy theo từng span.

    Trả ``None`` nếu dòng rỗng (không có span chứa chữ).
    """
    spans: list[TextSpan] = []
    for span in line_dict.get("spans", []):
        raw = span.get("text", "")
        if not raw:
            continue
        font = span.get("font", "") or ""
        flags = int(span.get("flags", 0))
        text, _label = convert_span_text(font, raw, config)
        spans.append(
            TextSpan(
                text=text,
                font=font,
                size=float(span.get("size", 0.0)),
                bold=_is_bold(font, flags),
                italic=_is_italic(font, flags),
            )
        )
    if not spans:
        return None
    bbox = tuple(float(v) for v in line_dict.get("bbox", (0.0, 0.0, 0.0, 0.0)))
    return Line(page=page_number, bbox=bbox, spans=tuple(spans))  # type: ignore[arg-type]


def extract_page(page: fitz.Page, config: DetectConfig) -> Page:
    """Trích một trang PyMuPDF thành :class:`model.Page` (chưa quyết trang ảnh)."""
    data = page.get_text("dict", sort=True)
    page_number = page.number + 1
    lines: list[Line] = []
    for block in data.get("blocks", []):
        for line_dict in block.get("lines", []):
            line = _extract_line(line_dict, page_number, config)
            if line is not None:
                lines.append(line)
    coverage, _lb = _page_image_coverage(page, config)
    rect = page.rect
    return Page(
        number=page_number,
        width=float(rect.width),
        height=float(rect.height),
        lines=tuple(lines),
        image_coverage=coverage,
        has_full_page_image=coverage >= config.scan_image_coverage,
    )


def render_page_png(page: fitz.Page, dpi: int) -> bytes:
    """Render nguyên trang thành PNG (dùng cho trang ảnh, US-A6)."""
    pix = page.get_pixmap(dpi=dpi)
    return pix.tobytes("png")


def _pdf_metadata(doc: fitz.Document, fallback_title: str) -> tuple[str, str | None]:
    meta = doc.metadata or {}
    title = (meta.get("title") or "").strip() or fallback_title
    author = (meta.get("author") or "").strip() or None
    return title, author


def extract_document(
    doc: fitz.Document, pdf_path: str | Path, config: DetectConfig | None = None
) -> Document:
    """Trích cả cuốn thành :class:`model.Document` (text model, **chưa** render trang ảnh).

    ``pdf_path`` dùng để tính ``pdf_sha256`` (định danh ổn định) và lấy tên file gốc.
    """
    config = config or DetectConfig()
    name = Path(pdf_path).name
    stem = Path(pdf_path).stem
    pages = tuple(extract_page(page, config) for page in doc)
    title, author = _pdf_metadata(doc, stem)
    return Document(
        pages=pages,
        source_pdf_name=name,
        pdf_sha256=sha256_file(pdf_path),
        title=title,
        author=author,
    )
