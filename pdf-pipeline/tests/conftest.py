"""Fixtures PDF **sinh bằng code** (PyMuPDF) — không cần sách thật, không commit sách.

Mỗi fixture trả về đường dẫn tới một PDF nhỏ trong thư mục tạm của pytest.
"""

from pathlib import Path

import pymupdf as fitz
import pytest

# Chữ Việt Unicode có dấu + vài chữ Hán (kiểm tra whitelist CJK).
VI_UNICODE_TEXT = "Tôi yêu tiếng Việt và học thuốc Đông y 穴 經 絡 mỗi ngày thật chăm chỉ."
# Giả lập TCVN3 bị rút ra thành rác (toàn ký tự Latin-1, font tên "sạch" là helv).
VI_TCVN3_GARBAGE = "T«i yªu ti·ng ViÖt vµ häc thuèc §«ng y mçi ngµy th·t ch¨m chØ h¬n"


def _write(doc: fitz.Document, path: Path) -> Path:
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def unicode_vi_pdf(tmp_path: Path) -> Path:
    """Trang chữ Việt Unicode + chữ Hán (dùng font cjk để glyph trích được đúng)."""
    doc = fitz.open()
    page = doc.new_page()
    tw = fitz.TextWriter(page.rect)
    tw.append((72, 100), VI_UNICODE_TEXT, font=fitz.Font("cjk"), fontsize=14)
    tw.write_text(page)
    return _write(doc, tmp_path / "unicode_vi.pdf")


@pytest.fixture
def tcvn3_garbage_pdf(tmp_path: Path) -> Path:
    """Trang chứa chuỗi kiểu TCVN3 (ký tự Latin-1), font tên sạch → bắt bằng heuristic."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), VI_TCVN3_GARBAGE, fontname="helv", fontsize=14)
    return _write(doc, tmp_path / "tcvn3_garbage.pdf")


@pytest.fixture
def scan_pdf(tmp_path: Path) -> Path:
    """Trang chỉ gồm một ảnh phủ kín, không có text layer → scan."""
    doc = fitz.open()
    page = doc.new_page()
    # Ảnh PNG đặc 1x1 phóng kín trang.
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 1, 1))
    pix.set_rect(pix.irect, (200, 180, 150))
    page.insert_image(page.rect, pixmap=pix)
    return _write(doc, tmp_path / "scan.pdf")


@pytest.fixture
def scan_ocr_pdf(tmp_path: Path) -> Path:
    """Trang ảnh phủ kín + lớp chữ ẩn (render mode 3) kiểu OCR → scan_ocr."""
    doc = fitz.open()
    page = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 1, 1))
    pix.set_rect(pix.irect, (210, 190, 160))
    page.insert_image(page.rect, pixmap=pix)
    page.insert_text(
        (72, 100),
        "day la lop chu an OCR nam ben duoi anh scan cua trang sach nay de minh hoa",
        render_mode=3,  # invisible — giống lớp text OCR
        fontname="helv",
        fontsize=12,
    )
    return _write(doc, tmp_path / "scan_ocr.pdf")


@pytest.fixture
def full_image_visible_text_pdf(tmp_path: Path) -> Path:
    """Ảnh nền phủ kín + chữ Việt Unicode **hiển thị** (không ẩn) → text_unicode, cờ ảnh-kín bật."""
    doc = fitz.open()
    page = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 1, 1))
    pix.set_rect(pix.irect, (235, 225, 200))
    page.insert_image(page.rect, pixmap=pix)
    tw = fitz.TextWriter(page.rect)
    tw.append((72, 120), VI_UNICODE_TEXT, font=fitz.Font("cjk"), fontsize=14)
    tw.write_text(page)  # render mode mặc định = 0 (hiển thị)
    return _write(doc, tmp_path / "full_image_visible_text.pdf")


@pytest.fixture
def scan_ocr_visible_book_pdf(tmp_path: Path) -> Path:
    """Sách scan kiểu ABBYY: NHIỀU trang ảnh phủ kín + chữ OCR **hiển thị** (render mode 0).

    Không có chữ ẩn → quy tắc mức trang không bắt; phải dựa quy tắc mức CUỐN (≥80% trang ảnh).
    """
    doc = fitz.open()
    for _ in range(6):
        page = doc.new_page()
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 1, 1))
        pix.set_rect(pix.irect, (235, 225, 200))
        page.insert_image(page.rect, pixmap=pix)
        tw = fitz.TextWriter(page.rect)
        tw.append((72, 120), VI_UNICODE_TEXT, font=fitz.Font("cjk"), fontsize=14)
        tw.write_text(page)  # render mode 0 = hiển thị
    doc.set_metadata({"producer": "ABBYY FineReader 11", "creator": "Foxit"})
    return _write(doc, tmp_path / "scan_ocr_visible_book.pdf")


@pytest.fixture
def empty_pdf(tmp_path: Path) -> Path:
    """Trang trắng, không chữ không ảnh → empty."""
    doc = fitz.open()
    doc.new_page()
    return _write(doc, tmp_path / "empty.pdf")


@pytest.fixture
def multi_page_pdf(tmp_path: Path) -> Path:
    """PDF nhiều trang trộn loại: 2 Unicode + 1 trắng → nhãn cuốn = text_unicode."""
    doc = fitz.open()
    for _ in range(2):
        page = doc.new_page()
        tw = fitz.TextWriter(page.rect)
        tw.append((72, 100), VI_UNICODE_TEXT, font=fitz.Font("cjk"), fontsize=14)
        tw.write_text(page)
    doc.new_page()  # trang trắng
    return _write(doc, tmp_path / "multi.pdf")


@pytest.fixture
def corrupt_pdf(tmp_path: Path) -> Path:
    """File .pdf hỏng (không phải PDF thật) → detect phải trả error, không crash."""
    path = tmp_path / "corrupt.pdf"
    path.write_bytes(b"%PDF-1.7\nnot a real pdf at all \x00\x01\x02 broken")
    return path


@pytest.fixture
def encrypted_pdf(tmp_path: Path) -> Path:
    """PDF mã hóa bằng mật khẩu → detect phải trả error 'password', không crash."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "secret", fontname="helv")
    path = tmp_path / "encrypted.pdf"
    doc.save(str(path), encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    doc.close()
    return path
