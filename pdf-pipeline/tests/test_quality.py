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
        Paragraph(
            text="Một đoạn văn tiếng Việt sạch sẽ, đủ dài và đúng dấu để không bị tính là vụn.",
            page=1,
        ),
        Paragraph(
            text="Đoạn thứ hai cũng bình thường và khá dài, lại có chèn chữ Hán 經 絡 minh hoạ.",
            page=1,
        ),
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


def test_short40_ratio_warns() -> None:
    # >25% đoạn < 40 ký tự → cảnh báo trộn cột / cắt vụn.
    blocks = [Paragraph(text="ngắn.", page=1) for _ in range(3)]
    blocks.append(
        Paragraph(text="Một đoạn dài đầy đủ hơn bốn mươi ký tự để không bị tính là vụn.", page=1)
    )
    r = check_blocks(blocks)
    assert r.pct_short40 > 0.25
    assert any("< 40 ký tự" in w for w in r.warnings)


def test_scan_ocr_warning() -> None:
    blocks = [
        Heading(text="C", level=1, page=1),
        Paragraph(text="Một đoạn văn tiếng Việt đủ dài và sạch sẽ, đúng dấu hoàn toàn.", page=1),
    ]
    r = check_blocks(blocks, is_scan_ocr=True)
    assert r.is_scan_ocr
    assert any("scan_ocr" in w for w in r.warnings)


def test_no_heading_warns() -> None:
    blocks = [Paragraph(text="chỉ có đoạn, không heading nào cả.", page=1)]
    r = check_blocks(blocks)
    assert any("heading" in w for w in r.warnings)


def test_garbage_blocks_removed_recorded() -> None:
    blocks = [Paragraph(text="Một đoạn văn tiếng Việt sạch và đủ dài để không vụn.", page=1)]
    r = check_blocks(
        blocks,
        garbage_blocks_removed=3,
        garbage_examples=("?>?H$ *íhA", "Àub1$ x"),
    )
    assert r.garbage_blocks_removed == 3
    assert r.garbage_examples == ("?>?H$ *íhA", "Àub1$ x")
    assert any("rác" in w and "bỏ" in w for w in r.warnings)


def test_garbage_long_low_score_warns() -> None:
    blocks = [Paragraph(text="Một đoạn văn tiếng Việt sạch và đủ dài để không vụn.", page=1)]
    r = check_blocks(blocks, garbage_long_low=2)
    assert any("điểm âm tiết Việt thấp" in w for w in r.warnings)


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


def test_text_coverage_by_page(tmp_path: Path) -> None:
    from sepia_pipeline.quality import text_coverage_by_page

    doc = fitz.open()
    p = doc.new_page(width=300, height=300)
    p.insert_text((30, 50), "mot hai ba bon nam sau bay tam", fontname="helv", fontsize=12)
    pdf = tmp_path / "c.pdf"
    doc.save(str(pdf))
    doc.close()

    # Khối chỉ chứa một nửa số chữ → độ phủ ~0.5, trang 1 vào low_pages.
    blocks = [Paragraph(text="mot hai ba bon", page=1)]
    rep = text_coverage_by_page(pdf, blocks)
    assert rep.n_pages == 1
    assert 0.3 < rep.coverage < 0.7
    assert rep.low_pages and rep.low_pages[0][0] == 1

    # Khối rỗng → trang vào empty_pages.
    rep2 = text_coverage_by_page(pdf, [])
    assert rep2.empty_pages == (1,)
