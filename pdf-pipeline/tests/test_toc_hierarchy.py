"""Test gán cấp heading theo mục lục in sẵn (toc_hierarchy.py) — hàm thuần trên Block."""

from sepia_pipeline.model import Heading, Paragraph
from sepia_pipeline.toc_hierarchy import (
    assign_heading_levels,
    canon,
    find_toc_region,
    parse_toc_entries,
    strip_diacritics,
)


def test_strip_diacritics_vietnamese() -> None:
    assert strip_diacritics("Đông y dưỡng sinh") == "Dong y duong sinh"
    assert canon("  PHƯƠNG PHÁP  XOA BÓP  ") == "phuong phap xoa bop"


def test_parse_entries_levels_by_marker() -> None:
    blocks = [
        Heading(text="MỤC LỤC", level=1, page=1),
        Paragraph(text="BƯỚC VÀO THẾ GIỚI ĐÔNG Y", page=1),  # caps → cấp 1
        Paragraph(text="1. Đôi nét về lịch sử Đông y .......... 22", page=1),  # số → cấp 2
        Paragraph(text="2. Âm dương chi phối sinh mệnh ... 24", page=1),
        Paragraph(text="• Xoa bóp trợ tim an thần .......... 100", page=1),  # bullet → cấp 3
    ]
    entries = parse_toc_entries(blocks)
    by = {e.title: e.level for e in entries}
    assert by["BƯỚC VÀO THẾ GIỚI ĐÔNG Y"] == 1
    assert by["Đôi nét về lịch sử Đông y"] == 2  # số trang + dấu dẫn đã bị bỏ
    assert by["Âm dương chi phối sinh mệnh"] == 2
    assert by["Xoa bóp trợ tim an thần"] == 3


def test_parse_splits_merged_entries() -> None:
    # Nhiều mục gộp trong một đoạn (OCR) → tách theo "N. <chữ>".
    merged = "1. Mục một .......... 22 2. Mục hai ...... 24 3. Mục ba . 26"
    entries = parse_toc_entries([Paragraph(text=merged, page=1)])
    titles = [e.title for e in entries]
    assert titles == ["Mục một", "Mục hai", "Mục ba"]
    assert all(e.level == 2 for e in entries)


def test_find_region_anchored_by_muc_luc() -> None:
    blocks = [
        Paragraph(text="Lời giới thiệu dài dòng không phải mục lục.", page=1),
        Heading(text="MỤC LỤC", level=1, page=2),
        Paragraph(text="1. Chương một .......... 10", page=2),
        Paragraph(text="2. Chương hai .......... 20", page=2),
        Paragraph(text="Đây là một đoạn văn thân bài rất dài không có dấu dẫn.", page=3),
        Paragraph(text="Một đoạn thân bài khác cũng dài và bình thường.", page=3),
        Paragraph(text="Và thêm một đoạn nữa để chắc chắn ra khỏi vùng mục lục.", page=3),
    ]
    region = find_toc_region(blocks)
    assert region is not None
    start, end = region
    assert start == 1  # tại "MỤC LỤC"
    assert end <= 4  # không nuốt thân bài


def test_no_printed_toc_is_fallback() -> None:
    blocks = [
        Heading(text="Chương 1", level=1, page=1),
        Paragraph(text="Nội dung thân bài.", page=1),
    ]
    rep = assign_heading_levels(blocks)
    assert rep.found_printed_toc is False
    assert rep.blocks is blocks  # giữ nguyên, không đổi cấp


def test_assign_matches_and_excludes_unmatched() -> None:
    blocks = [
        Heading(text="MỤC LỤC", level=1, page=1),
        Paragraph(text="PHƯƠNG PHÁP XOA BÓP DƯỠNG SINH", page=1),  # caps → cấp 1
        Paragraph(text="1. Phương pháp xoa bóp đơn giản dễ học .......... 86", page=1),
        Paragraph(text="• Xoa bóp trợ tim an thần .......... 100", page=1),
        Paragraph(text="Đoạn thân bài bình thường dài để thoát vùng mục lục.", page=2),
        Paragraph(text="Đoạn thân bài nữa cho chắc đã ra khỏi mục lục.", page=2),
        Paragraph(text="Và một đoạn thứ ba thật dài không có dấu dẫn nào cả.", page=2),
        # thân bài: các heading thật (thường in HOA)
        Heading(text="PHƯƠNG PHÁP XOA BÓP DƯỠNG SINH", level=1, page=3),
        Heading(text="PHƯƠNG PHÁP XOA BÓP ĐƠN GIẢN DỄ HỌC", level=1, page=4),
        Heading(text="XOA BÓP TRỢ TIM AN THẦN", level=1, page=5),
        Heading(text="HUYỆT TAM ÂM GIAO", level=1, page=6),  # KHÔNG có trong mục lục
    ]
    rep = assign_heading_levels(blocks)
    assert rep.found_printed_toc is True
    by = {b.text: b for b in rep.blocks if isinstance(b, Heading) and b.page >= 3}
    assert by["PHƯƠNG PHÁP XOA BÓP DƯỠNG SINH"].level == 1
    assert by["PHƯƠNG PHÁP XOA BÓP DƯỠNG SINH"].in_nav is True
    assert by["PHƯƠNG PHÁP XOA BÓP ĐƠN GIẢN DỄ HỌC"].level == 2
    assert by["XOA BÓP TRỢ TIM AN THẦN"].level == 3
    # Heading không khớp mục nào → cấp sâu nhất + NGOÀI nav.
    assert by["HUYỆT TAM ÂM GIAO"].level == 3
    assert by["HUYỆT TAM ÂM GIAO"].in_nav is False


def test_assign_is_immutable() -> None:
    orig = Heading(text="XOA BÓP TRỢ TIM AN THẦN", level=1, page=3, in_nav=True)
    blocks = [
        Heading(text="MỤC LỤC", level=1, page=1),
        Paragraph(text="• Xoa bóp trợ tim an thần .......... 100", page=1),
        Paragraph(text="Đoạn thân bài dài bình thường một.", page=2),
        Paragraph(text="Đoạn thân bài dài bình thường hai.", page=2),
        Paragraph(text="Đoạn thân bài dài bình thường ba.", page=2),
        orig,
    ]
    rep = assign_heading_levels(blocks)
    assert orig.level == 1  # object gốc KHÔNG bị sửa
    new = next(b for b in rep.blocks if isinstance(b, Heading) and b.page == 3)
    assert new.level == 3
