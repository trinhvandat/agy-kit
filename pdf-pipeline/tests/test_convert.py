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
    # v8: sách nhỏ (fixture vài đoạn ngắn) gộp vào 1 file — chia nhỏ chỉ khi > ~10k ký tự.
    assert report.epub.n_chapters >= 1
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


def test_born_digital_not_garbage_filtered(tmp_path: Path) -> None:
    """Sách born-digital (text_unicode, engine heuristic) → KHÔNG lọc rác, dù có heading nghi rác.

    Lọc rác chỉ bật cho nguồn OCR + tiếng Việt (Bug 2). Ở đây một heading điểm âm tiết Việt thấp
    vẫn phải được GIỮ (không bị bỏ oan) vì nguồn không phải OCR.
    """
    doc = fitz.open()
    page = doc.new_page(width=400, height=600)
    tw = fitz.TextWriter(page.rect)
    _append(tw, (40, 70), "Q W X Z", 20)  # heading điểm âm tiết Việt thấp (nếu lọc sẽ bị bỏ)
    _append(tw, (40, 120), "Đoạn văn tiếng Việt có dấu đầy đủ và khá dài cho đủ nội dung.", 10)
    _append(tw, (40, 140), "Một đoạn thứ hai cũng bằng tiếng Việt, dài và sạch sẽ rõ ràng.", 10)
    tw.write_text(page)
    doc.set_metadata({"title": "Sách thường", "author": "Tác giả"})
    pdf = tmp_path / "born.pdf"
    doc.save(str(pdf))
    doc.close()

    report = convert_pdf(pdf, tmp_path / "born.epub", run_check=False)
    assert report.engine == "heuristic"
    assert not report.is_scan_ocr
    assert report.quality.garbage_blocks_removed == 0  # gate tắt → không bỏ gì


def test_cli_convert(book_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "cli.epub"
    rc = main(["convert", str(book_pdf), "-o", str(out), "--no-check"])
    assert rc == 0
    assert out.exists()
