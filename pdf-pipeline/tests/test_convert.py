"""Test tích hợp lệnh convert (PDF → EPUB) + CLI."""

import shutil
from pathlib import Path

import pymupdf as fitz
import pytest

from sepia_pipeline.__main__ import main
from sepia_pipeline.convert import convert_pdf


def _append(tw: fitz.TextWriter, pos, text: str, size: float) -> None:
    tw.append(pos, text, font=fitz.Font("cjk"), fontsize=size)


@pytest.fixture
def book_pdf(tmp_path: Path) -> Path:
    """6 trang chữ (header + số trang lặp, heading cấp 1, đoạn vắt trang) + 1 trang ảnh."""
    doc = fitz.open()
    chapters = ["CHƯƠNG MỘT", "", "", "CHƯƠNG HAI", "", ""]
    for i, heading in enumerate(chapters, start=1):
        page = doc.new_page(width=400, height=600)
        tw = fitz.TextWriter(page.rect)
        _append(tw, (40, 20), "Tự học Đông y cơ bản", 8)  # header lặp
        _append(tw, (350, 20), str(10 + i), 8)  # số trang
        y = 90
        if heading:
            _append(tw, (40, y), heading, 20)
            y += 36
        _append(tw, (40, y), "Đoạn văn tiếng Việt có dấu đầy đủ kết thúc ở đây.", 10)
        _append(tw, (40, y + 18), "Đoạn hai bắt đầu và còn tiếp tục", 10)
        _append(tw, (40, y + 36), "sang các dòng kế tiếp cho đủ dài.", 10)
        tw.write_text(page)

    page = doc.new_page(width=400, height=600)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 1, 1))
    pix.set_rect(pix.irect, (210, 190, 160))
    page.insert_image(page.rect, pixmap=pix)

    doc.set_metadata({"title": "Tự học Đông y", "author": "Bùi Huy"})
    path = tmp_path / "book.pdf"
    doc.save(str(path))
    doc.close()
    return path


def test_convert_produces_epub(book_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "book.epub"
    report = convert_pdf(book_pdf, out, run_check=False)
    assert out.exists()
    assert report.epub.book_uid.startswith("sepia:")
    assert report.epub.n_chapters >= 2  # ≥ 2 chương cấp 1
    assert report.n_image_pages == 1
    assert report.epub.n_images == 1
    assert report.quality.n_headings >= 2


def test_convert_deterministic(book_pdf: Path, tmp_path: Path) -> None:
    a = tmp_path / "a.epub"
    b = tmp_path / "b.epub"
    convert_pdf(book_pdf, a, run_check=False)
    convert_pdf(book_pdf, b, run_check=False)
    assert a.read_bytes() == b.read_bytes()  # cùng PDF → EPUB giống hệt từng byte


def test_book_uid_stable_across_builds(book_pdf: Path, tmp_path: Path) -> None:
    r1 = convert_pdf(book_pdf, tmp_path / "1.epub", run_check=False)
    r2 = convert_pdf(book_pdf, tmp_path / "2.epub", run_check=False)
    assert r1.epub.book_uid == r2.epub.book_uid


def test_convert_epubcheck_valid(book_pdf: Path, tmp_path: Path) -> None:
    if shutil.which("java") is None:
        pytest.skip("không có Java → bỏ qua epubcheck")
    report = convert_pdf(book_pdf, tmp_path / "book.epub", run_check=True)
    assert report.quality.epubcheck is not None
    assert report.quality.epubcheck.startswith("epubcheck: HỢP LỆ"), report.quality.epubcheck


def test_cli_convert(book_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "cli.epub"
    rc = main(["convert", str(book_pdf), "-o", str(out), "--no-check"])
    assert rc == 0
    assert out.exists()
