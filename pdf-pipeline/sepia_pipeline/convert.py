"""Điều phối PDF → EPUB (lệnh ``convert``): extract → render trang ảnh → reflow → build → quality.

Giữ mỏng: mỗi bước là hàm thuần ở module riêng; ở đây chỉ nối chúng lại và mở/đóng tài liệu
PyMuPDF một lần. Không cấu hình toàn cục — mọi ngưỡng đi qua các *Config.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path

import pymupdf as fitz

from . import PIPELINE_VERSION
from .build_epub import EpubReport, build_epub, load_font_family
from .detect import DetectConfig, scan_ocr_book_signal
from .extract import extract_document, render_page_png
from .model import Document, Page
from .quality import QualityReport, check_blocks, run_epubcheck
from .reflow import ReflowConfig, build_blocks, collect_warnings, is_image_page

DEFAULT_OUT_DIR = Path(__file__).resolve().parent.parent / "out"


@dataclass(frozen=True)
class ConvertConfig:
    detect: DetectConfig = dataclasses.field(default_factory=DetectConfig)
    reflow: ReflowConfig = dataclasses.field(default_factory=ReflowConfig)
    image_dpi: int = 150


@dataclass(frozen=True)
class ConvertReport:
    pdf_name: str
    epub: EpubReport
    n_pages: int
    n_image_pages: int
    is_scan_ocr: bool
    quality: QualityReport
    warnings: tuple[str, ...]
    pipeline_version: int


def _render_image_pages(
    doc_model: Document, fitz_doc: fitz.Document, config: ConvertConfig
) -> Document:
    """Với mỗi trang được xem là trang ảnh (reflow), render PNG và gắn vào model."""
    pages: list[Page] = []
    for page in doc_model.pages:
        if is_image_page(page, config.reflow):
            png = render_page_png(fitz_doc[page.number - 1], config.image_dpi)
            pages.append(dataclasses.replace(page, image_png=png))
        else:
            pages.append(page)
    return dataclasses.replace(doc_model, pages=tuple(pages))


def default_out_path(pdf_path: str | Path) -> Path:
    return DEFAULT_OUT_DIR / (Path(pdf_path).stem + ".epub")


def convert_pdf(
    pdf_path: str | Path,
    out_path: str | Path | None = None,
    *,
    font_profile: str | None = None,
    config: ConvertConfig | None = None,
    run_check: bool = True,
) -> ConvertReport:
    """Chuyển một PDF thành EPUB sạch. Trả :class:`ConvertReport`.

    ``out_path`` mặc định = ``pdf-pipeline/out/<tên>.epub``. ``font_profile`` None → CSS ``serif``.
    """
    config = config or ConvertConfig()
    pdf_path = Path(pdf_path)
    out_path = Path(out_path) if out_path else default_out_path(pdf_path)
    font_family = load_font_family(font_profile)

    fitz_doc = fitz.open(str(pdf_path))
    try:
        doc_model = extract_document(fitz_doc, pdf_path, config.detect)
        doc_model = _render_image_pages(doc_model, fitz_doc, config)
    finally:
        fitz_doc.close()

    warnings = list(collect_warnings(doc_model, config.reflow))
    n_pages = len(doc_model.pages)
    n_image_pages = sum(1 for p in doc_model.pages if p.is_image_page)
    # Cuốn scan có lớp OCR hiển thị? (dùng chung tín hiệu với detect, tính trên model đã trích)
    full_image = sum(1 for p in doc_model.pages if p.has_full_page_image)
    texty = sum(1 for p in doc_model.pages if p.char_count >= config.detect.scan_min_chars)
    is_scan_ocr = scan_ocr_book_signal(n_pages, full_image, texty, config.detect)
    if n_pages and n_image_pages / n_pages > 0.5:
        warnings.append(
            f"{n_image_pages}/{n_pages} trang là ảnh — sách có thể chủ yếu scan "
            "(cân nhắc OCR, xem R-11); EPUB sẽ phần lớn là ảnh."
        )

    blocks = build_blocks(doc_model, config.reflow)
    epub_report = build_epub(
        doc_model,
        blocks,
        out_path,
        font_family=font_family,
        pipeline_version=PIPELINE_VERSION,
    )

    quality = check_blocks(blocks, is_scan_ocr=is_scan_ocr)
    if run_check:
        quality = dataclasses.replace(quality, epubcheck=run_epubcheck(str(out_path)))

    return ConvertReport(
        pdf_name=pdf_path.name,
        epub=epub_report,
        n_pages=n_pages,
        n_image_pages=n_image_pages,
        is_scan_ocr=is_scan_ocr,
        quality=quality,
        warnings=(*warnings, *quality.warnings),
        pipeline_version=PIPELINE_VERSION,
    )
