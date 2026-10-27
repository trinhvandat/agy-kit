"""Test lệnh ``ocr`` + phát hiện cache trong ``convert``.

Phần phát hiện cache chạy **mọi nơi** (stdlib). Lệnh ``ocr`` nhánh theo ``ocr_available()``: có
ocrmac (macOS + extra) → chạy thật; không (CI) → trả lỗi rõ. Cache dựng tay nên không cần Vision.
"""

from pathlib import Path

import pytest

from sepia_pipeline.__main__ import main
from sepia_pipeline.convert import convert_pdf
from sepia_pipeline.extract import sha256_file
from sepia_pipeline.ocr_cache import (
    OCR_ENGINE,
    OCR_RENDER,
    OcrCache,
    OcrLine,
    OcrPage,
    write_cache,
)
from sepia_pipeline.ocr_vision import ocr_available


def test_ocr_command(scan_pdf: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rc = main(["ocr", str(scan_pdf), "--cache-dir", str(tmp_path)])
    if ocr_available():  # macOS + extra ocr-mac
        assert rc == 0
        assert (tmp_path / f"{sha256_file(scan_pdf)}.json").exists()
    else:  # CI Ubuntu — không có Vision
        assert rc == 2
        assert "ocr-mac" in capsys.readouterr().err


def _make_cache(pdf: Path, engine: dict | None = None) -> OcrCache:
    sha = sha256_file(pdf)
    return OcrCache(
        book_uid=f"sepia:{sha}",
        pdf_sha256=sha,
        render=dict(OCR_RENDER),
        engine=engine or dict(OCR_ENGINE),
        engine_version={"macos_build": "X"},
        created="2026-10-27",
        pages=(OcrPage(page=0, lines=(OcrLine("x", (0.0, 0.0, 1.0, 1.0), 1.0),)),),
    )


def test_convert_scan_ocr_cache_miss(scan_ocr_visible_book_pdf: Path, tmp_path: Path) -> None:
    r = convert_pdf(
        scan_ocr_visible_book_pdf,
        tmp_path / "a.epub",
        run_check=False,
        ocr_cache_dir=tmp_path / "empty",
    )
    assert r.is_scan_ocr
    assert r.ocr_cache_status == "miss"
    assert any("sepia-pipeline ocr" in w for w in r.warnings)


def test_convert_scan_ocr_cache_present(scan_ocr_visible_book_pdf: Path, tmp_path: Path) -> None:
    cdir = tmp_path / "cache"
    write_cache(_make_cache(scan_ocr_visible_book_pdf), cdir)
    r = convert_pdf(
        scan_ocr_visible_book_pdf, tmp_path / "b.epub", run_check=False, ocr_cache_dir=cdir
    )
    assert r.ocr_cache_status == "present"


def test_convert_scan_ocr_cache_mismatch(scan_ocr_visible_book_pdf: Path, tmp_path: Path) -> None:
    cdir = tmp_path / "cache"
    write_cache(
        _make_cache(scan_ocr_visible_book_pdf, engine={**OCR_ENGINE, "name": "tesseract"}), cdir
    )
    r = convert_pdf(
        scan_ocr_visible_book_pdf, tmp_path / "c.epub", run_check=False, ocr_cache_dir=cdir
    )
    assert r.ocr_cache_status == "mismatch"


def test_cache_detection_does_not_change_epub(
    scan_ocr_visible_book_pdf: Path, tmp_path: Path
) -> None:
    """PR1 chỉ PHÁT HIỆN cache, chưa tiêu thụ → EPUB byte-identical dù có/không cache."""
    cdir = tmp_path / "cache"
    write_cache(_make_cache(scan_ocr_visible_book_pdf), cdir)
    a, b = tmp_path / "with.epub", tmp_path / "without.epub"
    convert_pdf(scan_ocr_visible_book_pdf, a, run_check=False, ocr_cache_dir=cdir)
    convert_pdf(scan_ocr_visible_book_pdf, b, run_check=False, ocr_cache_dir=tmp_path / "empty")
    assert a.read_bytes() == b.read_bytes()


def test_non_scan_book_no_cache_lookup(tmp_path: Path, unicode_vi_pdf: Path) -> None:
    """Sách không phải scan_ocr → không tra cache (status n/a)."""
    r = convert_pdf(unicode_vi_pdf, tmp_path / "u.epub", run_check=False)
    assert not r.is_scan_ocr
    assert r.ocr_cache_status == "n/a"
