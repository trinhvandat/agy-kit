"""Test Bước 5 — quality.py (kiểm tra nhẹ) + epubcheck (bỏ qua nếu không có Java)."""

import shutil
from pathlib import Path

import pymupdf as fitz

from sepia_pipeline.build_epub import build_epub
from sepia_pipeline.legacy_encoding import encode_tcvn3
from sepia_pipeline.model import Document, Heading, ImageBlock, Paragraph
from sepia_pipeline.quality import check_blocks, run_epubcheck


def test_clean_blocks_no_warnings() -> None:
    blocks = [
        Heading(text="CHƯƠNG MỘT", level=1, page=1),
        Paragraph(text="Một đoạn văn tiếng Việt sạch sẽ, đủ dài và đúng dấu.", page=1),
        Paragraph(text="Đoạn thứ hai cũng bình thường, có chữ Hán 經 絡.", page=1),
    ]
    r = check_blocks(blocks)
    assert r.n_paragraphs == 2 and r.n_headings == 1
    assert r.garbage_ratio < 0.02
    assert r.nfc_ok
    assert r.warnings == ()


def test_garbage_flagged() -> None:
    garbage = encode_tcvn3("huyệt vị kinh mạch điểm đặc biệt trên cơ thể con người")
    blocks = [
        Heading(text="C", level=1, page=1),
        Paragraph(text=garbage, page=1),
    ]
    r = check_blocks(blocks)
    assert r.garbage_ratio > 0.02
    assert any("rác" in w for w in r.warnings)


def test_no_heading_warns() -> None:
    blocks = [Paragraph(text="chỉ có đoạn, không heading nào cả.", page=1)]
    r = check_blocks(blocks)
    assert any("heading" in w for w in r.warnings)


def test_epubcheck_valid(tmp_path: Path) -> None:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 16, 16))
    pix.set_rect(pix.irect, (200, 180, 150))
    png = pix.tobytes("png")
    doc = Document(pages=(), source_pdf_name="x.pdf", pdf_sha256="a" * 64, title="T", author="A")
    blocks = [
        ImageBlock(png=png, page=1),
        Heading(text="CHƯƠNG MỘT", level=1, page=2),
        Paragraph(text="Nội dung tiếng Việt 經 絡.", page=2),
    ]
    out = tmp_path / "book.epub"
    build_epub(doc, blocks, out)
    summary = run_epubcheck(str(out))
    if shutil.which("java") is None:
        assert "không có Java" in summary
    else:
        assert summary.startswith("epubcheck: HỢP LỆ"), summary
