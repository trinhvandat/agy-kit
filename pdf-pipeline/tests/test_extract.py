"""Test Bước 1 — trích theo span (extract.py). PDF sinh bằng code (PyMuPDF)."""

from pathlib import Path

import pymupdf as fitz
import pytest

from sepia_pipeline.detect import DetectConfig
from sepia_pipeline.extract import extract_document, render_page_png, sha256_file
from sepia_pipeline.legacy_encoding import encode_tcvn3


def _append(tw: fitz.TextWriter, pos, text: str, size: float) -> None:
    tw.append(pos, text, font=fitz.Font("cjk"), fontsize=size)


@pytest.fixture
def small_pdf(tmp_path: Path) -> Path:
    """2 trang chữ + 1 trang ảnh. Trang chữ có header + số trang + heading cỡ lớn + body."""
    doc = fitz.open()
    for num, heading in [("12", "GIỚI THIỆU"), ("13", "")]:
        page = doc.new_page(width=400, height=600)
        tw = fitz.TextWriter(page.rect)
        _append(tw, (40, 20), "Chương 1 — Đông y cơ bản", 8)  # header lặp
        _append(tw, (350, 20), num, 8)  # số trang
        y = 90
        if heading:
            _append(tw, (40, y), heading, 20)  # heading cỡ lớn
            y += 40
        _append(tw, (40, y), "Đây là một đoạn văn tiếng Việt có dấu đầy đủ,", 10)
        _append(tw, (40, y + 20), "trải dài qua nhiều dòng để kiểm tra việc ghép", 10)
        _append(tw, (40, y + 40), "đoạn và chuyển mã font cũ cho đúng.", 10)
        tw.write_text(page)

    # Trang ảnh: ảnh phủ kín, rất ít chữ.
    page = doc.new_page(width=400, height=600)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 1, 1))
    pix.set_rect(pix.irect, (210, 190, 160))
    page.insert_image(page.rect, pixmap=pix)

    path = tmp_path / "small.pdf"
    doc.set_metadata({"title": "Tự học Đông y", "author": "Tác giả X"})
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def tcvn3_pdf(tmp_path: Path) -> Path:
    """Trang có span font cũ (.VnTime) chứa byte TCVN3 → extract phải chuyển về Unicode."""
    doc = fitz.open()
    page = doc.new_page(width=400, height=600)
    garbage = encode_tcvn3("châm cứu huyệt vị")
    # Dùng font built-in nhưng đặt tên span .VnTime không được; thay vào đó kiểm theo heuristic:
    # chèn chuỗi rác, font helv (tên sạch) → classify_span bắt bằng heuristic = legacy_other → GIỮ.
    # Để kiểm nhánh TCVN3 (font .Vn*), ta kiểm trực tiếp ở test_legacy_encoding; ở đây chỉ cần
    # extract không làm vỡ chuỗi Unicode bình thường.
    page.insert_text((40, 100), garbage, fontname="helv", fontsize=10)
    path = tmp_path / "tcvn3.pdf"
    doc.save(str(path))
    doc.close()
    return path


def test_sha256_stable(small_pdf: Path) -> None:
    assert sha256_file(small_pdf) == sha256_file(small_pdf)
    assert len(sha256_file(small_pdf)) == 64


def test_extract_structure(small_pdf: Path) -> None:
    doc = fitz.open(str(small_pdf))
    d = extract_document(doc, small_pdf, DetectConfig())
    doc.close()

    assert d.title == "Tự học Đông y"
    assert d.author == "Tác giả X"
    assert d.source_pdf_name == "small.pdf"
    assert d.book_uid.startswith("sepia:")
    assert len(d.pages) == 3

    p1 = d.pages[0]
    assert p1.number == 1
    assert p1.width == 400 and p1.height == 600
    # Heading cỡ 20 có mặt.
    sizes = {round(ln.dominant_size) for ln in p1.lines}
    assert 20 in sizes and 10 in sizes
    heading_lines = [ln for ln in p1.lines if round(ln.dominant_size) == 20]
    assert any("GIỚI THIỆU" in ln.text for ln in heading_lines)
    # Số trang + header nằm ở dải trên.
    assert any("Chương 1" in ln.text for ln in p1.lines)
    # Chữ Việt có dấu được giữ nguyên (không hỏng).
    assert any("tiếng Việt có dấu" in ln.text for ln in p1.lines)

    # Trang 3 là trang ảnh (ít chữ, ảnh phủ kín).
    p3 = d.pages[2]
    assert p3.has_full_page_image
    assert p3.char_count < 30


def test_render_page_png(small_pdf: Path) -> None:
    doc = fitz.open(str(small_pdf))
    png = render_page_png(doc[2], dpi=72)
    doc.close()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # magic PNG


def test_extract_does_not_corrupt_unicode(tcvn3_pdf: Path) -> None:
    doc = fitz.open(str(tcvn3_pdf))
    d = extract_document(doc, tcvn3_pdf, DetectConfig())
    doc.close()
    # Không crash, có ít nhất một dòng.
    assert sum(len(p.lines) for p in d.pages) >= 1
