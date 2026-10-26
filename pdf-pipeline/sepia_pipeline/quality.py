"""Bước 5 — Kiểm tra chất lượng **nhẹ** (docs/03 §8) + chạy epubcheck nếu có Java.

Không làm ground-truth/CER (quá nặng cho một người). Chỉ các tín hiệu tự động: tỷ lệ ký tự rác
(whitelist CJK — tái dùng heuristic của ``detect``), số đoạn/heading/ảnh, đoạn ngắn/dài bất thường,
và NFC nhất quán. In cảnh báo, **không chặn**.
"""

from __future__ import annotations

import shutil
import unicodedata
from dataclasses import dataclass, field

from .detect import _legacy_counts
from .model import Block, Heading, ImageBlock, Paragraph, Table


@dataclass(frozen=True)
class QualityConfig:
    short_para_chars: int = 3  # đoạn ngắn hơn (ký tự không-trắng) → nghi ghép dòng sai
    long_para_chars: int = 2500  # đoạn dài hơn → nghi thiếu ngắt đoạn
    garbage_ratio_warn: float = 0.02  # tỷ lệ ký tự rác vượt mức này → cảnh báo (nghi legacy sót)
    short40_chars: int = 40  # đoạn < bấy nhiêu ký tự = "vụn"
    short40_ratio_warn: float = 0.25  # > 25% đoạn vụn → nghi trộn cột / cắt dòng vụn


@dataclass(frozen=True)
class QualityReport:
    n_paragraphs: int
    n_headings: int
    n_images: int
    total_chars: int
    garbage_chars: int
    garbage_ratio: float
    short_paragraphs: int
    long_paragraphs: int
    short40_paragraphs: int
    pct_short40: float
    nfc_ok: bool
    is_scan_ocr: bool = False
    printed_toc_removed: int = 0
    garbage_blocks_removed: int = 0
    garbage_examples: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    epubcheck: str | None = None


def _non_space_len(text: str) -> int:
    return sum(1 for ch in text if not ch.isspace())


def _block_text(b: Block) -> str:
    if isinstance(b, Heading | Paragraph):
        return b.text
    if isinstance(b, Table):
        return " ".join(c for row in b.rows for c in row)
    return ""


@dataclass(frozen=True)
class CoverageReport:
    """So độ phủ chữ: lớp chữ PDF (PyMuPDF) vs chữ trong các khối sẽ dựng EPUB, theo trang."""

    total_pdf_chars: int
    total_block_chars: int
    coverage: float
    low_pages: tuple[tuple[int, int, int, float], ...]  # (trang, pdf_chars, block_chars, cov)
    empty_pages: tuple[int, ...]  # trang có chữ PDF nhưng khối rỗng
    n_pages: int
    max_block_page: int  # trang lớn nhất có khối → xác nhận đã xử lý tới đâu


def text_coverage_by_page(
    pdf_path, blocks: list[Block], *, low_threshold: float = 0.70
) -> CoverageReport:
    """Đếm ký tự lớp chữ PDF từng trang vs ký tự trong khối gán cho trang đó.

    Liệt kê trang phủ < ``low_threshold`` và trang có chữ PDF nhưng khối rỗng.
    """
    import pymupdf as fitz

    doc = fitz.open(str(pdf_path))
    pdf_chars = [_non_space_len(page.get_text("text")) for page in doc]
    doc.close()

    block_chars: dict[int, int] = {}
    for b in blocks:
        block_chars[b.page] = block_chars.get(b.page, 0) + _non_space_len(_block_text(b))

    low: list[tuple[int, int, int, float]] = []
    empty: list[int] = []
    for i, pc in enumerate(pdf_chars, start=1):
        bc = block_chars.get(i, 0)
        if pc <= 0:
            continue
        cov = bc / pc
        if bc == 0:
            empty.append(i)
        if cov < low_threshold:
            low.append((i, pc, bc, round(cov, 3)))

    total_pdf = sum(pdf_chars)
    total_block = sum(block_chars.values())
    return CoverageReport(
        total_pdf_chars=total_pdf,
        total_block_chars=total_block,
        coverage=(total_block / total_pdf) if total_pdf else 0.0,
        low_pages=tuple(low),
        empty_pages=tuple(empty),
        n_pages=len(pdf_chars),
        max_block_page=max(block_chars) if block_chars else 0,
    )


def check_blocks(
    blocks: list[Block],
    config: QualityConfig | None = None,
    *,
    is_scan_ocr: bool = False,
    printed_toc_removed: int = 0,
    garbage_blocks_removed: int = 0,
    garbage_examples: tuple[str, ...] = (),
    garbage_long_low: int = 0,
) -> QualityReport:
    """Chạy các kiểm tra nhẹ trên danh sách khối đã reflow.

    ``garbage_blocks_removed``/``garbage_examples``/``garbage_long_low`` do bước lọc rác
    (:func:`reflow.drop_garbage_blocks`) cung cấp — ghi lại để báo cáo (số khối rác đã bỏ + ví dụ,
    và số khối dài điểm thấp vẫn giữ nhưng đáng ngờ).
    """
    config = config or QualityConfig()
    paras = [b for b in blocks if isinstance(b, Paragraph)]
    headings = [b for b in blocks if isinstance(b, Heading)]
    images = [b for b in blocks if isinstance(b, ImageBlock)]

    all_text = "\n".join(b.text for b in blocks if isinstance(b, Heading | Paragraph))
    suspect, letters = _legacy_counts(all_text)
    denom = suspect + letters
    garbage_ratio = suspect / denom if denom else 0.0

    short = sum(1 for p in paras if _non_space_len(p.text) < config.short_para_chars)
    long_ = sum(1 for p in paras if _non_space_len(p.text) > config.long_para_chars)
    short40 = sum(1 for p in paras if _non_space_len(p.text) < config.short40_chars)
    pct_short40 = short40 / len(paras) if paras else 0.0
    nfc_ok = all(
        b.text == unicodedata.normalize("NFC", b.text)
        for b in blocks
        if isinstance(b, Heading | Paragraph)
    )

    warnings: list[str] = []
    if is_scan_ocr:
        warnings.append("cuốn là scan_ocr — chất lượng text phụ thuộc lớp OCR gốc (ABBYY…)")
    if garbage_ratio > config.garbage_ratio_warn:
        warnings.append(
            f"tỷ lệ ký tự rác {garbage_ratio:.3f} > {config.garbage_ratio_warn} "
            f"({suspect} ký tự) — nghi font cũ chưa chuyển hết"
        )
    if pct_short40 > config.short40_ratio_warn:
        warnings.append(
            f"{pct_short40:.0%} đoạn < {config.short40_chars} ký tự "
            f"({short40}/{len(paras)}) — nghi trộn cột / cắt dòng vụn"
        )
    if not headings:
        warnings.append("không tìm thấy heading nào — TOC sẽ rỗng, kiểm lại ngưỡng cỡ chữ")
    if short:
        warnings.append(f"{short} đoạn quá ngắn (< {config.short_para_chars} ký tự)")
    if long_:
        warnings.append(f"{long_} đoạn quá dài (> {config.long_para_chars} ký tự), nghi thiếu ngắt")
    if not nfc_ok:
        warnings.append("có text chưa chuẩn hóa NFC")
    if garbage_blocks_removed:
        ex = "; ".join(garbage_examples[:3])
        warnings.append(
            f"đã bỏ {garbage_blocks_removed} khối rác (điểm âm tiết Việt thấp)"
            f"{f' — vd: {ex}' if ex else ''}"
        )
    if garbage_long_low:
        warnings.append(
            f"{garbage_long_low} khối DÀI điểm âm tiết Việt thấp (giữ lại, nghi OCR/font hỏng)"
        )

    return QualityReport(
        n_paragraphs=len(paras),
        n_headings=len(headings),
        n_images=len(images),
        total_chars=denom,
        garbage_chars=suspect,
        garbage_ratio=garbage_ratio,
        short_paragraphs=short,
        long_paragraphs=long_,
        short40_paragraphs=short40,
        pct_short40=pct_short40,
        nfc_ok=nfc_ok,
        is_scan_ocr=is_scan_ocr,
        printed_toc_removed=printed_toc_removed,
        garbage_blocks_removed=garbage_blocks_removed,
        garbage_examples=tuple(garbage_examples),
        warnings=tuple(warnings),
    )


def run_epubcheck(epub_path: str) -> str:
    """Chạy epubcheck (nếu có Java). Trả chuỗi tóm tắt; không raise nếu thiếu công cụ."""
    if shutil.which("java") is None:
        return "chưa kiểm epubcheck (không có Java)"
    try:
        from epubcheck import EpubCheck  # type: ignore[import-untyped]
    except Exception:
        return "chưa kiểm epubcheck (thiếu package epubcheck)"
    try:
        result = EpubCheck(epub_path)
    except Exception as exc:  # noqa: BLE001 - công cụ ngoài, chỉ báo cáo
        return f"epubcheck lỗi khi chạy: {type(exc).__name__}: {exc}"
    messages = list(getattr(result, "messages", []) or [])
    n_err = sum(1 for m in messages if getattr(m, "level", "") in ("ERROR", "FATAL"))
    n_warn = sum(1 for m in messages if getattr(m, "level", "") == "WARNING")
    if result.valid:
        return f"epubcheck: HỢP LỆ (valid){f', {n_warn} cảnh báo' if n_warn else ''}"
    return f"epubcheck: KHÔNG hợp lệ — {n_err} lỗi, {n_warn} cảnh báo"
