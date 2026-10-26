"""Test reflow.py — hàm thuần trên mô hình (không cần PyMuPDF)."""

from sepia_pipeline.model import Document, Heading, ImageBlock, Line, Page, Paragraph, TextSpan
from sepia_pipeline.reflow import (
    ReflowConfig,
    build_blocks,
    collapse_ws,
    ends_sentence,
    find_repeating_bands,
    is_page_number_line,
    normalize_text,
)

W, H = 400.0, 600.0


def ln(
    page: int, y: float, text: str, *, size: float = 10.0, x: float = 40.0, bold: bool = False
) -> Line:
    span = TextSpan(text=text, font="X", size=size, bold=bold)
    return Line(page=page, bbox=(x, y, x + 300, y + size + 2), spans=(span,))


# --- helper nhỏ ---------------------------------------------------------------


def test_ends_sentence() -> None:
    assert ends_sentence("Một câu đầy đủ.")
    assert ends_sentence("Hỏi gì vậy?")
    assert ends_sentence("Trích dẫn.”")  # bỏ nháy đóng rồi xét
    assert ends_sentence("liệt kê:")
    assert not ends_sentence("dòng chưa xong và")
    assert not ends_sentence("từ ghép - nối")


def test_is_page_number_line() -> None:
    assert is_page_number_line("12")
    assert is_page_number_line("- 12 -")
    assert is_page_number_line("Trang 12")
    assert is_page_number_line("Page 7")
    assert is_page_number_line("iv")
    assert not is_page_number_line("Chương 1: mở đầu")
    assert not is_page_number_line("12 vị thuốc quý")


def test_collapse_and_normalize() -> None:
    assert collapse_ws("a   b\n c ") == "a b c"
    assert normalize_text("  Đông    y \n cơ bản ") == "Đông y cơ bản"


# --- header/footer lặp --------------------------------------------------------


def _text_page(
    number: int,
    body_lines: list[Line],
    *,
    header: str | None,
    number_text: str | None,
) -> Page:
    lines: list[Line] = []
    if header is not None:
        lines.append(ln(number, 20, header, size=8))
    if number_text is not None:
        lines.append(ln(number, 20, number_text, size=8, x=350))
    lines.extend(body_lines)
    return Page(number=number, width=W, height=H, lines=tuple(lines))


def test_find_repeating_bands() -> None:
    cfg = ReflowConfig()
    pages = [
        _text_page(i, [ln(i, 200, "thân bài")], header="Chương 1 Đông y", number_text=str(10 + i))
        for i in range(1, 6)
    ]
    doc = Document(pages=tuple(pages), source_pdf_name="x.pdf", pdf_sha256="h")
    repeating = find_repeating_bands(doc, cfg)
    assert "chương đông y" in repeating  # chữ số đã bị bỏ khi so khớp


def test_build_blocks_strips_heads_joins_paragraphs_and_image() -> None:
    cfg = ReflowConfig()
    # 5 trang chữ + 1 trang ảnh.
    p1 = _text_page(
        1,
        [
            ln(1, 60, "GIỚI THIỆU", size=20),  # heading
            ln(1, 100, "Đoạn một kết thúc ở đây."),  # đoạn riêng (có dấu chấm)
            ln(1, 120, "Đoạn hai bắt đầu và chưa"),  # chưa kết thúc → nối sang trang 2
        ],
        header="Chương 1 Đông y",
        number_text="11",
    )
    p2 = _text_page(
        2,
        [ln(2, 100, "kết thúc tại trang sau.")],  # nối tiếp đoạn hai
        header="Chương 1 Đông y",
        number_text="12",
    )
    fillers = [
        _text_page(
            i,
            [ln(i, 100, f"nội dung trang {i} đầy đủ.")],
            header="Chương 1 Đông y",
            number_text=str(10 + i),
        )
        for i in range(3, 6)
    ]
    img = Page(
        number=6,
        width=W,
        height=H,
        lines=(),
        image_coverage=0.99,
        has_full_page_image=True,
        image_png=b"\x89PNG\r\n\x1a\nFAKE",
    )
    doc = Document(pages=(p1, p2, *fillers, img), source_pdf_name="x.pdf", pdf_sha256="h")

    blocks = build_blocks(doc, cfg)
    texts = [(type(b).__name__, getattr(b, "text", "<img>")) for b in blocks]

    # Header + số trang bị bỏ: không block nào chứa "Chương 1 Đông y" hay số trang trần.
    assert all("Chương 1 Đông y" not in t for _, t in texts)

    # Có heading "GIỚI THIỆU".
    assert any(isinstance(b, Heading) and b.text == "GIỚI THIỆU" and b.level == 1 for b in blocks)

    # Đoạn hai được nối qua trang: tồn tại một paragraph ghép đủ.
    assert any(
        isinstance(b, Paragraph) and b.text == "Đoạn hai bắt đầu và chưa kết thúc tại trang sau."
        for b in blocks
    )
    # Đoạn một vẫn là paragraph riêng.
    assert any(isinstance(b, Paragraph) and b.text == "Đoạn một kết thúc ở đây." for b in blocks)

    # Trang ảnh thành ImageBlock đúng vị trí cuối.
    assert isinstance(blocks[-1], ImageBlock)
    assert blocks[-1].page == 6


def test_pure_symbol_paragraphs_dropped() -> None:
    cfg = ReflowConfig()
    page = Page(
        number=1,
        width=W,
        height=H,
        lines=(
            ln(1, 100, "•"),  # rác trang trí → bỏ
            ln(1, 140, "Đoạn văn thật sự có nội dung."),
            ln(1, 180, "»"),  # rác → bỏ
        ),
    )
    doc = Document(pages=(page,), source_pdf_name="x.pdf", pdf_sha256="h")
    paras = [b for b in build_blocks(doc, cfg) if isinstance(b, Paragraph)]
    assert len(paras) == 1
    assert paras[0].text == "Đoạn văn thật sự có nội dung."


def test_two_line_heading_merged() -> None:
    cfg = ReflowConfig()
    body = tuple(
        ln(1, 140 + i * 16, f"Dòng thân bài bình thường số {i} cho đủ nhiều.") for i in range(8)
    )
    page = Page(
        number=1,
        width=W,
        height=H,
        lines=(
            ln(1, 60, "TÌM HIỂU", size=24),
            ln(1, 92, "VỀ CÁC VỊ THUỐC ĐÔNG Y", size=24),
            *body,
        ),
    )
    doc = Document(pages=(page,), source_pdf_name="x.pdf", pdf_sha256="h")
    blocks = build_blocks(doc, cfg)
    headings = [b for b in blocks if isinstance(b, Heading)]
    assert len(headings) == 1
    assert headings[0].text == "TÌM HIỂU VỀ CÁC VỊ THUỐC ĐÔNG Y"


def test_big_font_intro_run_becomes_paragraph() -> None:
    # Nhiều dòng cỡ lớn liên tiếp (lời giới thiệu in to) → ĐOẠN VĂN, không phải chuỗi heading.
    cfg = ReflowConfig()
    big_lines = tuple(
        ln(1, 60 + i * 30, f"Dòng giới thiệu in chữ to số {i} khá dài cho đủ.", size=18)
        for i in range(5)
    )
    # Thân bài cỡ 10 để cỡ 18 là "lớn hơn thân bài" (ứng viên heading) rồi bị hạ vì >2 dòng.
    body = tuple(ln(1, 260 + i * 16, f"Thân bài số {i} đầy đủ nội dung.") for i in range(10))
    page = Page(number=1, width=W, height=H, lines=(*big_lines, *body))
    doc = Document(pages=(page,), source_pdf_name="x.pdf", pdf_sha256="h")
    blocks = build_blocks(doc, cfg)
    # Khối chữ-to 5 dòng > max_heading_lines(2) → gộp thành MỘT đoạn văn, không có heading.
    assert not any(isinstance(b, Heading) for b in blocks)
    assert any(isinstance(b, Paragraph) and "giới thiệu in chữ to" in b.text for b in blocks)


def test_paragraph_break_on_indent() -> None:
    cfg = ReflowConfig()
    page = Page(
        number=1,
        width=W,
        height=H,
        lines=(
            ln(1, 100, "dòng đầu chưa kết thúc và", x=40),
            ln(1, 116, "dòng thụt vào sâu hơn", x=80),  # thụt > 14pt → đoạn mới
        ),
    )
    doc = Document(pages=(page,), source_pdf_name="x.pdf", pdf_sha256="h")
    paras = [b for b in build_blocks(doc, cfg) if isinstance(b, Paragraph)]
    assert len(paras) == 2


def test_drop_printed_toc_run() -> None:
    from sepia_pipeline.reflow import drop_printed_toc

    blocks = [
        Heading(text="MỤC LỤC", level=1, page=1),
        Paragraph(text="Chương một ........................... 5", page=1),
        Paragraph(text="Chương hai ........................... 12", page=1),
        Paragraph(text="Chương ba ............................ 20", page=1),
        Paragraph(text="Đây là đoạn thân bài bình thường không phải mục lục.", page=2),
    ]
    kept, removed = drop_printed_toc(blocks)
    assert removed == 3
    assert all("..." not in getattr(b, "text", "") for b in kept)
    assert any("thân bài bình thường" in getattr(b, "text", "") for b in kept)


def test_toc_single_line_kept() -> None:
    from sepia_pipeline.reflow import drop_printed_toc

    # Dòng lẻ có chấm dẫn (không thành chuỗi) → KHÔNG bị bỏ.
    blocks = [
        Paragraph(text="Xem thêm phần phụ lục ........ 99", page=1),
        Paragraph(text="Một đoạn văn thường sau đó, dài và bình thường.", page=1),
    ]
    kept, removed = drop_printed_toc(blocks)
    assert removed == 0
    assert len(kept) == 2


def test_drop_printed_toc_table() -> None:
    from sepia_pipeline.model import Table
    from sepia_pipeline.reflow import drop_printed_toc

    toc_table = Table(
        rows=(("Chương một", "..... 5"), ("Chương hai", "..... 12"), ("Chương ba", "..... 20")),
        page=1,
    )
    blocks = [toc_table, Paragraph(text="Thân bài thật sự bắt đầu ở đây và khá dài.", page=2)]
    kept, removed = drop_printed_toc(blocks)
    assert removed == 3  # 3 hàng
    assert len(kept) == 1
