"""Test gán cấp heading theo mục lục in sẵn (toc_hierarchy.py) — hàm thuần trên Block.

PIPELINE_VERSION 11: cấp 1 = CHƯƠNG của mục lục in sẵn ("Chương N: <tên>"), mỗi chương neo MỘT
heading thân bài (lần sau mục lục; không thấy heading tên chương → neo vào mục con đầu). Nhãn nav
lấy chữ mục lục in sẵn (Heading.nav_label); chữ thân bài (text) không đổi.
"""

from sepia_pipeline.model import Heading, Paragraph
from sepia_pipeline.toc_hierarchy import (
    assign_heading_levels,
    canon,
    find_toc_region,
    match_key,
    parse_chapters,
    parse_toc_entries,
    strip_diacritics,
)

# Ba đoạn thân bài dài (không dấu dẫn) để thoát vùng mục lục (find_toc_region cần 3 khối không-TOC).
_EXIT = [
    Paragraph(text="Đoạn thân bài dài bình thường một không có dấu dẫn gì cả.", page=3),
    Paragraph(text="Đoạn thân bài dài bình thường hai không có dấu dẫn gì cả.", page=3),
    Paragraph(text="Đoạn thân bài dài bình thường ba không có dấu dẫn gì cả.", page=3),
]


def test_strip_diacritics_vietnamese() -> None:
    assert strip_diacritics("Đông y dưỡng sinh") == "Dong y duong sinh"
    assert canon("  PHƯƠNG PHÁP  XOA BÓP  ") == "phuong phap xoa bop"


def test_match_key_strips_internal_punctuation() -> None:
    # OCR đổi ',' thành '.' / rơi dấu — match_key vẫn khớp.
    assert match_key("TỰ CHỮA ĐAU ĐẦU, NÓNG ĐẦU") == match_key("TỰ CHỮA ĐẠU ĐẦU. NÓNG ĐẦU")


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
    assert by["Đôi nét về lịch sử Đông y"] == 2
    assert by["Xoa bóp trợ tim an thần"] == 3


def test_parse_splits_merged_entries() -> None:
    merged = "1. Mục một .......... 22 2. Mục hai ...... 24 3. Mục ba . 26"
    entries = parse_toc_entries([Paragraph(text=merged, page=1)])
    assert [e.title for e in entries] == ["Mục một", "Mục hai", "Mục ba"]


def test_find_region_anchored_by_muc_luc() -> None:
    blocks = [
        Paragraph(text="Lời giới thiệu dài dòng không phải mục lục.", page=1),
        Heading(text="MỤC LỤC", level=1, page=2),
        Paragraph(text="1. Chương một .......... 10", page=2),
        Paragraph(text="2. Chương hai .......... 20", page=2),
        *_EXIT,
    ]
    region = find_toc_region(blocks)
    assert region is not None and region[0] == 1 and region[1] <= 4


def test_no_printed_toc_is_fallback() -> None:
    blocks = [
        Heading(text="Chương 1", level=1, page=1),
        Paragraph(text="Nội dung thân bài.", page=1),
    ]
    rep = assign_heading_levels(blocks)
    assert rep.found_printed_toc is False
    assert rep.blocks is blocks  # giữ nguyên, không đổi cấp


def test_parse_chapters_from_markers_split_and_inline() -> None:
    region = [
        Heading(text="MỤC LỤC", level=1, page=1),
        Paragraph(text="Chương 1", page=1),  # marker tách rời (OCR)
        Paragraph(text="BƯỚC VÀO THẾ GIỚI", page=1),  # tên chương ở khối sau
        Paragraph(text="1. Mục con một .......... 10", page=1),
        Paragraph(text="Chương 2 TÌM HIỂU VỀ THUỐC", page=1),  # marker + tên cùng dòng
        Paragraph(text="1. Mục con hai .......... 20", page=1),
    ]
    chapters = parse_chapters(region)
    assert [c.number for c in chapters] == [1, 2]
    assert chapters[0].label == "Chương 1: BƯỚC VÀO THẾ GIỚI"
    assert chapters[1].title == "TÌM HIỂU VỀ THUỐC"
    assert any(e.title == "Mục con một" for e in chapters[0].children)


def test_level1_is_chapter_anchored_in_body_with_printed_label() -> None:
    blocks = [
        Heading(text="MỤC LỤC", level=1, page=1),
        Paragraph(text="Chương 1", page=1),
        Paragraph(text="PHƯƠNG PHÁP XOA BÓP DƯỠNG SINH", page=1),  # tên chương (mục lục)
        Paragraph(text="1. Phương pháp đơn giản .......... 10", page=1),
        *_EXIT,
        # Thân bài: heading tên chương (OCR hơi khác dấu) + một mục con.
        Heading(text="PHƯƠNG PHÁP XOA BÓP DƯƠNG SINH", level=1, page=5),
        Heading(text="PHƯƠNG PHÁP ĐƠN GIẢN", level=1, page=6),
        Heading(text="HUYỆT KHÔNG CÓ TRONG MỤC LỤC", level=1, page=7),
    ]
    rep = assign_heading_levels(blocks)
    assert rep.n_chapters == 1 and rep.anchored_chapters == 1
    hs = {b.page: b for b in rep.blocks if isinstance(b, Heading) and b.page >= 5}
    ch = hs[5]
    assert ch.level == 1 and ch.in_nav is True
    assert ch.nav_label == "Chương 1: PHƯƠNG PHÁP XOA BÓP DƯỠNG SINH"  # chữ mục lục in sẵn
    assert ch.text == "PHƯƠNG PHÁP XOA BÓP DƯƠNG SINH"  # chữ THÂN BÀI không đổi
    assert hs[6].level == 2 and hs[6].in_nav is True
    # Heading không có trong mục lục → ngoài nav, cấp sâu nhất.
    assert hs[7].in_nav is False and hs[7].level == 3
    # Đúng MỘT mục cấp 1.
    assert sum(1 for b in rep.blocks if isinstance(b, Heading) and b.in_nav and b.level == 1) == 1


def test_chapter_fallback_to_first_child_when_title_missing() -> None:
    blocks = [
        Heading(text="MỤC LỤC", level=1, page=1),
        Paragraph(text="Chương 1", page=1),
        Paragraph(text="BƯỚC VÀO THẾ GIỚI ĐÔNG Y", page=1),  # tên chương (vắng heading thân bài)
        Paragraph(text="1. Đôi nét về lịch sử .......... 10", page=1),
        Paragraph(text="2. Âm dương sinh mệnh chi phối .......... 12", page=1),
        *_EXIT,
        # Thân bài: tên chương VẮNG; mục con đầu "Đôi nét" cũng vắng; mục con 2 có heading.
        Heading(text="ÂM DƯƠNG SINH MỆNH CHI PHỐI", level=1, page=5),
    ]
    rep = assign_heading_levels(blocks)
    assert rep.anchored_chapters == 1
    anchor = next(b for b in rep.blocks if isinstance(b, Heading) and b.page == 5)
    assert anchor.level == 1 and anchor.in_nav is True
    assert anchor.nav_label == "Chương 1: BƯỚC VÀO THẾ GIỚI ĐÔNG Y"
    assert any("neo vào mục con đầu" in w for w in rep.warnings)


def test_repeated_series_title_not_level1() -> None:
    blocks = [
        Heading(text="MỤC LỤC", level=1, page=1),
        Paragraph(text="Chương 1", page=1),
        Paragraph(text="CHỦ ĐỀ CHÍNH CỦA SÁCH", page=1),
        Paragraph(text="1. Mục nhỏ đầu tiên .......... 10", page=1),
        *_EXIT,
        Heading(text="CHỦ ĐỀ CHÍNH CỦA SÁCH", level=1, page=5),  # chương (anchor)
        Heading(text="TIÊU ĐỀ LOẠT LẶP LẠI NHIỀU LẦN", level=1, page=6),  # loạt lặp, ngoài mục lục
        Heading(text="TIÊU ĐỀ LOẠT LẶP LẠI NHIỀU LẦN", level=1, page=7),
        Heading(text="TIÊU ĐỀ LOẠT LẶP LẠI NHIỀU LẦN", level=1, page=8),
    ]
    rep = assign_heading_levels(blocks)
    level1 = [b for b in rep.blocks if isinstance(b, Heading) and b.in_nav and b.level == 1]
    assert len(level1) == 1  # chỉ chương, không có tiêu đề loạt lặp
    repeats = [b for b in rep.blocks if isinstance(b, Heading) and b.page in (6, 7, 8)]
    assert all(b.in_nav is False for b in repeats)


def test_body_text_never_mutated() -> None:
    blocks = [
        Heading(text="MỤC LỤC", level=1, page=1),
        Paragraph(text="Chương 1 BƯỚC VÀO THẾ GIỚI", page=1),
        Paragraph(text="1. Mục con đầu tiên dài .......... 10", page=1),
        *_EXIT,
        Heading(text="BƯỚC VÀO THẾ GIỚI", level=1, page=5),
        Heading(text="MỤC CON ĐẦU TIÊN DÀI", level=1, page=6),
    ]
    before = [b.text for b in blocks if isinstance(b, Heading)]
    rep = assign_heading_levels(blocks)
    after = [b.text for b in rep.blocks if isinstance(b, Heading)]
    assert before == after  # text thân bài bất biến


def test_assign_is_immutable() -> None:
    orig = Heading(text="BƯỚC VÀO THẾ GIỚI ĐÔNG Y", level=2, page=5, in_nav=True)
    blocks = [
        Heading(text="MỤC LỤC", level=1, page=1),
        Paragraph(text="Chương 1", page=1),
        Paragraph(text="BƯỚC VÀO THẾ GIỚI ĐÔNG Y", page=1),
        Paragraph(text="1. Mục con .......... 10", page=1),
        *_EXIT,
        orig,
    ]
    rep = assign_heading_levels(blocks)
    assert orig.level == 2 and orig.nav_label is None  # object gốc KHÔNG bị sửa
    new = next(b for b in rep.blocks if isinstance(b, Heading) and b.page == 5)
    assert new.level == 1 and new.nav_label == "Chương 1: BƯỚC VÀO THẾ GIỚI ĐÔNG Y"
