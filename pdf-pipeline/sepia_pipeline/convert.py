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
from .model import Document, Heading, ImageBlock, Page, Paragraph
from .ocr_cache import DEFAULT_CACHE_DIR, OCR_ENGINE, OCR_SCHEMA, OcrCache, read_cache
from .quality import QualityReport, check_blocks, run_epubcheck
from .reflow import (
    GarbageFilterResult,
    ReflowConfig,
    build_blocks,
    collect_warnings,
    drop_garbage_blocks,
    drop_printed_toc,
    drop_running_headers,
    is_image_page,
    tidy_bullet_markers,
)
from .toc_hierarchy import assign_heading_levels
from .vietnamese import looks_vietnamese

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
    engine: str  # "heuristic" | "docling"
    quality: QualityReport
    warnings: tuple[str, ...]
    pipeline_version: int
    ocr_cache_status: str = "n/a"  # "n/a" | "present" | "miss" | "mismatch" (xem _ocr_cache_status)


ENGINES = ("auto", "heuristic", "docling")


def _ocr_cache_status(
    pdf_sha256: str, cache_dir: str | Path
) -> tuple[str, tuple[str, ...], OcrCache | None]:
    """Tra cache OCR Vision cho cuốn scan_ocr. Trả ``(state, warnings, cache|None)``; chỉ đọc đĩa.

    - không có cache → ``miss`` (+ nhắc chạy ``sepia-pipeline ocr``), cache ``None``.
    - khác schema/engine → ``mismatch`` (bỏ qua, dùng v4), cache ``None``.
    - hợp lệ → ``present`` (route hybrid dùng), kèm ``cache``.
    """
    cache = read_cache(cache_dir, pdf_sha256)
    if cache is None:
        return (
            "miss",
            (
                "sách scan_ocr: chưa có cache OCR Vision → đang dùng lớp chữ ẩn (v4). "
                "Chạy `sepia-pipeline ocr <pdf>` trên Mac để bật OCR-lại chất lượng cao (SPIKE-5).",
            ),
            None,
        )
    if cache.ocr_schema != OCR_SCHEMA or cache.engine.get("name") != OCR_ENGINE["name"]:
        return (
            "mismatch",
            (
                f"cache OCR có nhưng khác schema/engine (schema {cache.ocr_schema}, "
                f"engine {cache.engine.get('name')}) → bỏ qua, dùng v4. Cần OCR lại.",
            ),
            None,
        )
    return (
        "present",
        (f"cache OCR Vision có ({len(cache.pages)} trang, {cache.n_lines} dòng) — route hybrid.",),
        cache,
    )


def _choose_engine(engine: str, is_scan_ocr: bool) -> tuple[str, list[str]]:
    """Chọn engine + cảnh báo. ``auto`` → docling cho scan_ocr (nếu có), còn lại heuristic."""
    from .docling_adapter import INSTALL_HINT, docling_available

    if engine == "heuristic":
        return "heuristic", []
    if engine == "docling":
        if not docling_available():
            raise RuntimeError(f"--engine docling nhưng {INSTALL_HINT}")
        return "docling", []
    # auto
    if is_scan_ocr:
        if docling_available():
            return "docling", []
        return "heuristic", [
            f"sách scan_ocr nên dùng Docling nhưng {INSTALL_HINT} "
            "→ tạm dùng heuristic (chất lượng thấp hơn trên sách scan)."
        ]
    return "heuristic", []


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
    engine: str = "auto",
    config: ConvertConfig | None = None,
    run_check: bool = True,
    ocr_cache_dir: str | Path | None = None,
) -> ConvertReport:
    """Chuyển một PDF thành EPUB sạch. Trả :class:`ConvertReport`.

    ``out_path`` mặc định = ``pdf-pipeline/out/<tên>.epub``. ``font_profile`` None → CSS ``serif``.
    ``engine`` ∈ {auto, heuristic, docling}: ``auto`` dùng Docling cho sách ``scan_ocr`` (nếu đã cài
    extra), còn lại dùng heuristic PyMuPDF.
    """
    if engine not in ENGINES:
        raise ValueError(f"engine phải thuộc {ENGINES}, nhận '{engine}'")
    config = config or ConvertConfig()
    pdf_path = Path(pdf_path)
    out_path = Path(out_path) if out_path else default_out_path(pdf_path)
    font_family = load_font_family(font_profile)

    # Luôn trích bằng PyMuPDF để lấy metadata (title/author/sha → bookUid) + tín hiệu scan_ocr.
    fitz_doc = fitz.open(str(pdf_path))
    try:
        doc_model = extract_document(fitz_doc, pdf_path, config.detect)
        n_pages = len(doc_model.pages)
        full_image = sum(1 for p in doc_model.pages if p.has_full_page_image)
        texty = sum(1 for p in doc_model.pages if p.char_count >= config.detect.scan_min_chars)
        is_scan_ocr = scan_ocr_book_signal(n_pages, full_image, texty, config.detect)
        engine_used, warnings = _choose_engine(engine, is_scan_ocr)
        if engine_used == "heuristic":
            doc_model = _render_image_pages(doc_model, fitz_doc, config)
    finally:
        fitz_doc.close()

    # Phát hiện cache OCR Vision (chỉ sách scan_ocr). PR ocr-ingest-cache: CHỈ cảnh báo, chưa tiêu
    # thụ (route hybrid dùng ở PIPELINE_VERSION 5) → EPUB không đổi so với v4.
    ocr_cache_status = "n/a"
    ocr_cache_obj: OcrCache | None = None
    if is_scan_ocr:
        cache_dir = ocr_cache_dir if ocr_cache_dir is not None else DEFAULT_CACHE_DIR
        ocr_cache_status, cache_warnings, ocr_cache_obj = _ocr_cache_status(
            doc_model.pdf_sha256, cache_dir
        )
        warnings += cache_warnings

    if engine_used == "docling":
        # Route HYBRID (ADR-009): có cache Vision hợp lệ → bố cục Docling + chữ Vision theo toạ độ.
        # Không có cache → giữ lớp chữ ẩn (Docling + ABBYY) như v4.
        if ocr_cache_status == "present" and ocr_cache_obj is not None:
            from .ocr_hybrid import extract_blocks_hybrid

            blocks, hybrid_report = extract_blocks_hybrid(pdf_path, ocr_cache_obj)
            warnings += hybrid_report.warnings
        else:
            from .docling_adapter import extract_blocks_docling

            blocks = extract_blocks_docling(pdf_path)
    else:
        warnings += collect_warnings(doc_model, config.reflow)
        n_img_pages = sum(1 for p in doc_model.pages if p.is_image_page)
        if n_pages and n_img_pages / n_pages > 0.5:
            warnings.append(
                f"{n_img_pages}/{n_pages} trang là ảnh — sách có thể chủ yếu scan "
                "(cân nhắc OCR, xem R-11); EPUB sẽ phần lớn là ảnh."
            )
        blocks = build_blocks(doc_model, config.reflow)

    # Đường Docling: bỏ tiêu đề chạy đầu trang lặp (dùng ``top_ratio`` từ bbox để chỉ xét khối ở
    # dải mép trên). TẮT MẶC ĐỊNH — xem ``ReflowConfig.drop_running_headers_enabled`` & spike-4 §v4.
    running_headers_removed = 0
    running_header_examples: tuple[str, ...] = ()
    if engine_used == "docling" and config.reflow.drop_running_headers_enabled:
        header_result = drop_running_headers(blocks, config.reflow)
        blocks = header_result.kept
        running_headers_removed = header_result.removed
        running_header_examples = header_result.examples

    # Lọc dòng rác theo âm tiết Việt — CHỈ bật khi (a) nguồn là OCR (cuốn scan_ocr hoặc đường
    # Docling) VÀ (b) sách là tiếng Việt. Sách born-digital (text_unicode, legacy sau chuyển mã)
    # và sách không phải tiếng Việt KHÔNG lọc — để không bỏ oan nội dung thật (vd heading tiếng Anh
    # chấm 0 điểm âm tiết Việt). Xem docs/03 §8.
    # Đổi dấu đầu dòng OCR sai (»/®) → "• " trước khi lọc rác/mục lục (Việc 3, issue #20).
    # CHỈ áp cho nguồn OCR — sách born-digital có thể dùng »/® thật (vd nháy đóng, đăng ký nhãn
    # hiệu) và không nên bị viết lại.
    is_ocr_source = is_scan_ocr or engine_used == "docling"
    if is_ocr_source:
        blocks = tidy_bullet_markers(blocks)

    book_text = " ".join(b.text for b in blocks if isinstance(b, Heading | Paragraph))
    if is_ocr_source and looks_vietnamese(book_text):
        garbage = drop_garbage_blocks(blocks, config.reflow)
        blocks = garbage.kept
    else:
        garbage = GarbageFilterResult(kept=blocks, removed=(), long_low_score=())

    # v10: gán cấp heading theo MỤC LỤC IN SẴN (trước khi bỏ nó). Route Vision-OCR cho mọi heading
    # cùng cỡ → nếu không có bước này, nav phẳng (mọi mục cấp 1). Không có mục lục in sẵn → giữ cấp
    # theo cỡ chữ (fallback) + cảnh báo.
    toc_h = assign_heading_levels(blocks)
    blocks = toc_h.blocks
    if toc_h.found_printed_toc:
        warnings.append(
            f"toc-hierarchy: {toc_h.matched_headings} heading khớp mục lục in sẵn "
            f"({toc_h.toc_entries} mục), cấp {toc_h.level_counts}; "
            f"{len(toc_h.unmatched_toc_titles)} mục lục không khớp heading nào"
        )
        for t in toc_h.unmatched_toc_titles:
            warnings.append(f"  mục lục không khớp: {t}")
    else:
        warnings.append(
            "toc-hierarchy: KHÔNG thấy mục lục in sẵn → giữ cấp heading theo cỡ chữ "
            "(nav có thể phẳng)"
        )

    blocks, toc_removed = drop_printed_toc(blocks, config.reflow)
    n_image_pages = sum(1 for b in blocks if isinstance(b, ImageBlock))
    epub_report = build_epub(
        doc_model,
        blocks,
        out_path,
        font_family=font_family,
        pipeline_version=PIPELINE_VERSION,
    )

    quality = check_blocks(
        blocks,
        is_scan_ocr=is_scan_ocr,
        printed_toc_removed=toc_removed,
        garbage_blocks_removed=len(garbage.removed),
        garbage_examples=garbage.removed,
        garbage_long_low=len(garbage.long_low_score),
        running_headers_removed=running_headers_removed,
        running_header_examples=running_header_examples,
    )
    if run_check:
        quality = dataclasses.replace(quality, epubcheck=run_epubcheck(str(out_path)))

    return ConvertReport(
        pdf_name=pdf_path.name,
        epub=epub_report,
        n_pages=n_pages,
        n_image_pages=n_image_pages,
        is_scan_ocr=is_scan_ocr,
        engine=engine_used,
        quality=quality,
        warnings=(*warnings, *quality.warnings),
        pipeline_version=PIPELINE_VERSION,
        ocr_cache_status=ocr_cache_status,
    )
