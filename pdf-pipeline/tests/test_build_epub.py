"""Test Bước 4 — build_epub.py: định danh ổn định, chia chương, đầu ra tất định, font profile."""

import zipfile
from pathlib import Path

import pymupdf as fitz
import pytest
from ebooklib import epub

from sepia_pipeline import PIPELINE_VERSION
from sepia_pipeline.build_epub import _blocks_to_chapters, build_epub, load_font_family
from sepia_pipeline.model import Document, Heading, ImageBlock, Paragraph


def _png() -> bytes:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 100, 100))  # ≥ _IMG_MIN_EDGE để không bị bỏ
    pix.set_rect(pix.irect, (210, 190, 160))
    return pix.tobytes("png")


PNG = _png()


def _doc() -> Document:
    return Document(
        pages=(),
        source_pdf_name="dongy.pdf",
        pdf_sha256="a" * 64,
        title="Tự học Đông y",
        author="Tác giả X",
    )


def _blocks() -> list:
    return [
        ImageBlock(png=PNG, page=1),  # bìa (front matter)
        Heading(text="CHƯƠNG MỘT", level=1, page=2),
        Paragraph(text="Đoạn mở đầu của chương một.", page=2),
        Heading(text="Mục nhỏ", level=2, page=3),
        Paragraph(text="Nội dung mục nhỏ với dấu tiếng Việt đầy đủ.", page=3),
        Heading(text="CHƯƠNG HAI", level=1, page=4),
        Paragraph(text="Chương hai có chữ Hán 經 絡 huyệt vị.", page=4),
    ]


def test_identifier_and_structure(tmp_path: Path) -> None:
    out = tmp_path / "book.epub"
    report = build_epub(_doc(), _blocks(), out)
    assert report.book_uid == "sepia:" + "a" * 64
    # Nội dung nhỏ (< ngưỡng) → gộp hết vào MỘT file (v8: chia theo ~10k ký tự).
    assert report.n_chapters == 1
    assert report.n_images == 1

    book = epub.read_epub(str(out))
    assert book.get_metadata("DC", "identifier")[0][0] == "sepia:" + "a" * 64
    assert book.get_metadata("DC", "language")[0][0] == "vi"
    # pipeline-version ghi trong metadata.
    metas = book.get_metadata("OPF", "meta")
    props = {opts.get("property"): val for val, opts in metas}
    assert props.get("sepia:pipeline-version") == str(PIPELINE_VERSION)


def test_deterministic_bytes(tmp_path: Path) -> None:
    a = tmp_path / "a.epub"
    b = tmp_path / "b.epub"
    build_epub(_doc(), _blocks(), a)
    build_epub(_doc(), _blocks(), b)
    assert a.read_bytes() == b.read_bytes()  # giống hệt từng byte


def test_mimetype_first_and_stored(tmp_path: Path) -> None:
    out = tmp_path / "book.epub"
    build_epub(_doc(), _blocks(), out)
    with zipfile.ZipFile(out) as z:
        infos = z.infolist()
        assert infos[0].filename == "mimetype"
        assert infos[0].compress_type == zipfile.ZIP_STORED
        assert z.read("mimetype") == b"application/epub+zip"
        # ngày cố định (tất định)
        assert all(i.date_time == (1980, 1, 1, 0, 0, 0) for i in infos)


def test_small_sections_pack_into_one_file() -> None:
    # Nhiều mục nhỏ (tổng < target) → GỘP vào một file; mọi heading vẫn vào nav.
    blocks = []
    for i in range(3):
        blocks.append(Heading(text=f"CHƯƠNG {i}", level=1, page=i + 1))
        blocks.append(Heading(text="Mục con", level=2, page=i + 1))
        blocks.append(Paragraph(text="nội dung.", page=i + 1))
    chapters, _images, nav = _blocks_to_chapters(_doc(), blocks)
    assert len(chapters) == 1  # tổng vài chục ký tự → một file
    assert len(nav) == 6  # cả h1 + h2 đều vào nav


def test_breaks_at_heading_once_over_target() -> None:
    # Mỗi mục ~1000 ký tự, target=3000 → tách ở heading sau khi vượt target; file BẮT ĐẦU ở heading.
    blocks = []
    for i in range(9):
        blocks.append(Heading(text=f"Mục {i}", level=1, page=i + 1))
        blocks.append(Paragraph(text="x" * 1000, page=i + 1))
    chapters, _images, nav = _blocks_to_chapters(_doc(), blocks, target_chars=3000, max_chars=4000)
    # 9×~1000 ≈ 9000 ký tự, target 3000 → ~3 file (mỗi file gộp ~3 mục).
    assert 2 <= len(chapters) <= 4
    assert len(nav) == 9
    # mỗi file (trừ file đầu nếu bắt đầu bằng nội dung) bắt đầu bằng một heading.
    for c in chapters:
        assert c.html_body.lstrip().startswith("<h")


def test_coarsest_level_breaks_not_subheadings() -> None:
    # Có h1 + h2: tách ưu tiên ở h1 (coarsest); h2 chỉ là mục con nav, KHÔNG tách sớm theo h2.
    blocks = []
    for i in range(4):
        blocks.append(Heading(text=f"CHƯƠNG {i}", level=1, page=i + 1))
        blocks.append(Paragraph(text="x" * 2000, page=i + 1))
        blocks.append(Heading(text="Mục con", level=2, page=i + 1))
        blocks.append(Paragraph(text="y" * 500, page=i + 1))
    chapters, _images, nav = _blocks_to_chapters(_doc(), blocks, target_chars=3000, max_chars=9000)
    # Tách ở h1 khi ≥3000; h2 (ngưỡng = max 9000) không gây tách giữa chương.
    assert all(c.html_body.lstrip().startswith("<h1") for c in chapters)


def test_many_sections_target_file_count() -> None:
    # Giống Docling: hàng trăm heading cấp 1 → gộp theo ~target, không mỗi heading một file.
    blocks: list = []
    for i in range(200):
        blocks.append(Heading(text=f"Mục {i}", level=1, page=1))
        blocks.append(Paragraph(text="x" * 800, page=1))
    chapters, _images, nav = _blocks_to_chapters(_doc(), blocks, target_chars=7000, max_chars=10000)
    # 200×~830 ≈ 166k ký tự / ~8k → ~20 file (KHÔNG 1, KHÔNG 200).
    assert 15 <= len(chapters) <= 28
    assert len(nav) == 200


def test_size_cap_splits_large_section() -> None:
    big = "x" * 5000
    blocks = [Heading(text="CHƯƠNG MỘT", level=1, page=1)]
    blocks += [Paragraph(text=big, page=1) for _ in range(10)]
    chapters, _images, _nav = _blocks_to_chapters(
        _doc(), blocks, target_chars=7000, max_chars=10000
    )
    # 50k ký tự / 10k → ~5–6 file; file đầu giữ heading, còn lại "(tiếp)".
    assert len(chapters) >= 4
    assert chapters[0].title == "CHƯƠNG MỘT"
    assert all("(tiếp)" in c.title for c in chapters[1:])


def test_table_not_split_even_if_large() -> None:
    from sepia_pipeline.model import Table

    big_cell = "x" * 6000
    blocks = [
        Heading(text="CHƯƠNG MỘT", level=1, page=1),
        Table(rows=((big_cell, big_cell), (big_cell, big_cell)), page=1),  # ~24k ký tự, > max
    ]
    chapters, _images, _nav = _blocks_to_chapters(
        _doc(), blocks, target_chars=7000, max_chars=10000
    )
    # Bảng là khối NGUYÊN KHỐI → không bị cắt; nằm trọn trong một file.
    table_files = [c for c in chapters if "<table>" in c.html_body]
    assert len(table_files) == 1
    assert chapters[0].html_body.count("<table>") == 1


def test_heading_not_orphaned_before_huge_paragraph() -> None:
    # heading + đoạn khổng lồ (> max): heading PHẢI ở cùng file với đoạn đó, không thành file rỗng.
    blocks = [
        Heading(text="CHƯƠNG MỘT", level=1, page=1),
        Paragraph(text="x" * 12000, page=1),
        Paragraph(text="y" * 500, page=1),
    ]
    chapters, _images, _nav = _blocks_to_chapters(
        _doc(), blocks, target_chars=7000, max_chars=10000
    )
    assert chapters[0].title == "CHƯƠNG MỘT"
    assert '<h1 id="h1">CHƯƠNG MỘT</h1>' in chapters[0].html_body
    assert "x" * 12000 in chapters[0].html_body  # đoạn to ở CÙNG file với heading
    assert len(chapters) == 2  # đoạn 500 sang file "(tiếp)"


def test_image_embedded(tmp_path: Path) -> None:
    out = tmp_path / "book.epub"
    build_epub(_doc(), _blocks(), out)
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert any(n.endswith("images/img_0000.png") for n in names)


def test_table_and_caption_rendered(tmp_path: Path) -> None:
    from sepia_pipeline.model import Table

    blocks = [
        Heading(text="CHƯƠNG MỘT", level=1, page=1),
        ImageBlock(png=PNG, page=1, caption="Hình 1: sơ đồ kinh lạc"),
        Table(rows=(("Huyệt", "Vị trí"), ("Hợp cốc", "mu bàn tay")), page=1),
    ]
    out = tmp_path / "book.epub"
    build_epub(_doc(), blocks, out)
    with zipfile.ZipFile(out) as z:
        body = z.read(next(n for n in z.namelist() if n.endswith("chap_0001.xhtml"))).decode()
    assert "<figcaption>Hình 1: sơ đồ kinh lạc</figcaption>" in body
    assert "<table>" in body and "<td>Hợp cốc</td>" in body
    # Bảng hẹp (2 cột) giữ nguyên dạng cũ — KHÔNG class "wide", không thead.
    assert 'class="wide"' not in body and "<thead>" not in body


def test_wide_table_emits_cards_markup(tmp_path: Path) -> None:
    # Bảng ≥4 cột (Việc 4): hàng đầu = <thead><th>, ô thân mang data-label (nhãn cột) để app hiện
    # dạng "thẻ" trên màn hẹp. Hàng tiêu đề KHÔNG lặp trong <tbody>.
    from sepia_pipeline.model import Table

    blocks = [
        Table(
            rows=(
                ("Huyệt", "Vị trí", "Công dụng", "Cách bấm"),
                ("Hợp cốc", "mu bàn tay", "giảm đau", "day 1 phút"),
            ),
            page=1,
        ),
    ]
    out = tmp_path / "book.epub"
    build_epub(_doc(), blocks, out)
    with zipfile.ZipFile(out) as z:
        body = z.read(next(n for n in z.namelist() if n.endswith("chap_0001.xhtml"))).decode()
    # ebooklib in đẹp (thêm xuống dòng giữa thẻ) → kiểm từng mảnh, không yêu cầu liền mạch.
    assert '<table class="wide">' in body
    assert "<thead>" in body and "<th>Huyệt</th>" in body
    assert '<td data-label="Vị trí">mu bàn tay</td>' in body
    assert body.count("<tbody>") == 1
    assert body.count("Hợp cốc") == 1  # hàng dữ liệu còn; tiêu đề không nhân đôi


def test_font_profile_default_is_serif() -> None:
    assert load_font_family(None) == "serif"


def test_font_profile_dongy_loads() -> None:
    fam = load_font_family("dongy")
    assert "Literata" in fam and "serif" in fam


def test_font_profile_unknown_raises() -> None:
    with pytest.raises(KeyError):
        load_font_family("khong-co-profile-nay")


def test_font_profile_written_to_css(tmp_path: Path) -> None:
    out = tmp_path / "book.epub"
    build_epub(_doc(), _blocks(), out, font_family=load_font_family("dongy"))
    with zipfile.ZipFile(out) as z:
        css_name = next(n for n in z.namelist() if n.endswith("main.css"))
        css = z.read(css_name).decode("utf-8")
    assert "Literata" in css


def _photo_png(w: int = 1600, h: int = 400) -> bytes:
    # Ảnh nhiều màu (gradient) → bị coi là ảnh chụp → JPEG + resize.
    import pymupdf as fitz

    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, w, h))
    for x in range(w):
        for y in range(0, h, 50):
            pix.set_rect(fitz.IRect(x, y, x + 1, y + 50), (x % 256, (x * 2) % 256, (y + x) % 256))
    return pix.tobytes("png")


def test_large_photo_becomes_jpeg_and_resized(tmp_path: Path) -> None:
    blocks = [Heading(text="C", level=1, page=1), ImageBlock(png=_photo_png(), page=1)]
    out = tmp_path / "b.epub"
    build_epub(_doc(), blocks, out)
    with zipfile.ZipFile(out) as z:
        imgs = [n for n in z.namelist() if n.startswith("EPUB/images/")]
        assert imgs and imgs[0].endswith(".jpg")  # nhiều màu → JPEG
        import io

        from PIL import Image

        im = Image.open(io.BytesIO(z.read(imgs[0])))
        assert max(im.size) <= 1200  # đã đổi cỡ


def test_tiny_image_dropped(tmp_path: Path) -> None:
    import pymupdf as fitz

    tiny = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 20, 20))
    tiny.set_rect(tiny.irect, (10, 10, 10))
    blocks = [Heading(text="C", level=1, page=1), ImageBlock(png=tiny.tobytes("png"), page=1)]
    out = tmp_path / "b.epub"
    build_epub(_doc(), blocks, out)
    with zipfile.ZipFile(out) as z:
        assert not [n for n in z.namelist() if n.startswith("EPUB/images/")]


def test_tiny_image_with_caption_becomes_paragraph(tmp_path: Path) -> None:
    import pymupdf as fitz

    tiny = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 20, 20))
    tiny.set_rect(tiny.irect, (10, 10, 10))
    blocks = [
        Heading(text="C", level=1, page=1),
        ImageBlock(png=tiny.tobytes("png"), page=1, caption="Hợp cốc"),
    ]
    out = tmp_path / "b.epub"
    build_epub(_doc(), blocks, out)
    with zipfile.ZipFile(out) as z:
        body = z.read(next(n for n in z.namelist() if n.endswith("chap_0001.xhtml"))).decode()
        assert not [n for n in z.namelist() if n.startswith("EPUB/images/")]
    assert "<p>Hợp cốc</p>" in body
    assert "<figcaption>" not in body  # không có figcaption trần (HTML hợp lệ)


def test_caption_with_quotes_escaped(tmp_path: Path) -> None:
    import shutil

    blocks = [
        Heading(text="C", level=1, page=1),
        ImageBlock(png=PNG, page=1, caption='Huyệt "Hợp cốc" & <đồ hình>'),
    ]
    out = tmp_path / "b.epub"
    build_epub(_doc(), blocks, out)
    with zipfile.ZipFile(out) as z:
        body = z.read(next(n for n in z.namelist() if n.endswith("chap_0001.xhtml"))).decode()
    assert 'alt="Huyệt &quot;Hợp cốc&quot; &amp; &lt;đồ hình&gt;"' in body
    if shutil.which("java"):
        from sepia_pipeline.quality import run_epubcheck

        assert run_epubcheck(str(out)).startswith("epubcheck: HỢP LỆ")


def test_nav_three_levels_and_in_nav_exclusion(tmp_path: Path) -> None:
    """v10: nav lồng 3 cấp; heading in_nav=False render <h> nhưng KHÔNG vào nav."""
    blocks = [
        Heading(text="CHƯƠNG MỘT", level=1, page=1),
        Heading(text="Mục đánh số", level=2, page=1),
        Heading(text="Gạch đầu dòng", level=3, page=1),
        Heading(text="Tiêu đề ngoài mục lục", level=3, page=1, in_nav=False),
        Paragraph(text="Nội dung thân bài có dấu tiếng Việt đầy đủ ở đây.", page=1),
    ]
    out = tmp_path / "book.epub"
    build_epub(_doc(), blocks, out)
    with zipfile.ZipFile(out) as z:
        nav = next(n for n in z.namelist() if n.endswith("nav.xhtml"))
        html = z.read(nav).decode("utf-8")
        body = "".join(
            z.read(n).decode("utf-8") for n in z.namelist() if n.endswith(".xhtml") and n != nav
        )
    # Heading ngoài mục lục vẫn render <h3> trong thân bài…
    assert "Tiêu đề ngoài mục lục" in body
    # …nhưng KHÔNG xuất hiện trong nav.
    assert "Tiêu đề ngoài mục lục" not in html
    # Ba mục còn lại vào nav, lồng nhau (ít nhất 3 <ol> = 3 cấp).
    for t in ("CHƯƠNG MỘT", "Mục đánh số", "Gạch đầu dòng"):
        assert t in html
    assert html.count("<ol") >= 3
