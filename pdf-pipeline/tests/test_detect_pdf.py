"""Cycle 4 — adapter PyMuPDF: detect_page / detect_pdf trên PDF sinh bằng code."""

from pathlib import Path

from sepia_pipeline.detect import (
    EMPTY,
    LEGACY_OTHER,
    SCAN,
    TEXT_UNICODE,
    BookResult,
    detect_pdf,
)


def test_unicode_book(unicode_vi_pdf: Path) -> None:
    res = detect_pdf(unicode_vi_pdf)
    assert isinstance(res, BookResult)
    assert res.error is None
    assert res.label == TEXT_UNICODE
    assert res.n_pages == 1
    assert res.page_distribution.get(TEXT_UNICODE) == 1


def test_unicode_book_keeps_han_without_flagging_garbage(unicode_vi_pdf: Path) -> None:
    # Chữ Hán không bị đếm là rác → không gắn cờ legacy.
    res = detect_pdf(unicode_vi_pdf)
    assert res.pages[0].legacy_ratio < 0.05


def test_tcvn3_garbage_book_flagged_legacy(tcvn3_garbage_pdf: Path) -> None:
    res = detect_pdf(tcvn3_garbage_pdf)
    # Font tên sạch (helv) nhưng text là rác → heuristic gắn legacy_other.
    assert res.label == LEGACY_OTHER
    assert res.pages[0].legacy_ratio > 0.15


def test_scan_book(scan_pdf: Path) -> None:
    res = detect_pdf(scan_pdf)
    assert res.label == SCAN
    assert res.scan_pages == 1


def test_empty_book(empty_pdf: Path) -> None:
    res = detect_pdf(empty_pdf)
    assert res.label == EMPTY
    assert res.empty_pages == 1


def test_multi_page_distribution(multi_page_pdf: Path) -> None:
    res = detect_pdf(multi_page_pdf)
    assert res.n_pages == 3
    assert res.page_distribution.get(TEXT_UNICODE) == 2
    assert res.page_distribution.get(EMPTY) == 1
    assert res.label == TEXT_UNICODE  # đa số


def test_corrupt_pdf_returns_error_not_crash(corrupt_pdf: Path) -> None:
    res = detect_pdf(corrupt_pdf)
    assert res.error is not None
    assert res.label is None
    assert res.n_pages == 0


def test_encrypted_pdf_returns_error_not_crash(encrypted_pdf: Path) -> None:
    res = detect_pdf(encrypted_pdf)
    assert res.error is not None
    assert "password" in res.error.lower() or "mật khẩu" in res.error.lower()


def test_missing_file_returns_error(tmp_path: Path) -> None:
    res = detect_pdf(tmp_path / "khong-ton-tai.pdf")
    assert res.error is not None
