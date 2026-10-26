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
    # Tách ở h1 (2 mốc): front(ảnh) + CHƯƠNG MỘT (gồm h2 Mục nhỏ) + CHƯƠNG HAI.
    assert report.n_chapters == 3
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


def test_split_at_coarsest_heading() -> None:
    # 3 h1 (ít) → tách ở h1; h2 KHÔNG tách file (thành mục con trong nav).
    blocks = []
    for i in range(3):
        blocks.append(Heading(text=f"CHƯƠNG {i}", level=1, page=i + 1))
        blocks.append(Heading(text="Mục con", level=2, page=i + 1))
        blocks.append(Paragraph(text="nội dung.", page=i + 1))
    chapters, _images, nav = _blocks_to_chapters(_doc(), blocks)
    assert len(chapters) == 3  # chỉ cắt ở 3 h1
    assert len(nav) == 6  # cả h1 + h2 đều vào nav


def test_one_h1_stays_one_file() -> None:
    # 1 h1 + nhiều h2 → MỘT file (h2 là mục con nav), không tách theo h2.
    blocks = [
        Heading(text="CHƯƠNG MỘT", level=1, page=1),
        Paragraph(text="a.", page=1),
        Heading(text="Mục A", level=2, page=1),
        Paragraph(text="b.", page=1),
        Heading(text="Mục B", level=2, page=1),
        Paragraph(text="c.", page=1),
    ]
    chapters, _images, nav = _blocks_to_chapters(_doc(), blocks)
    assert len(chapters) == 1
    assert [e.level for e in nav] == [1, 2, 2]


def test_many_headings_split_by_size_only() -> None:
    # Giống Docling: hàng trăm heading cấp 1 → KHÔNG tách theo heading, chỉ theo kích thước.
    blocks: list = []
    for i in range(200):
        blocks.append(Heading(text=f"Mục {i}", level=1, page=1))
        blocks.append(Paragraph(text="x" * 800, page=1))
    chapters, _images, nav = _blocks_to_chapters(_doc(), blocks, max_file_bytes=20_000)
    # 200×~800B ≈ 160KB+ → vài chục file, KHÔNG phải 200.
    assert len(chapters) < 30
    assert len(nav) == 200  # mọi heading vẫn vào nav


def test_size_cap_splits_large_chapter() -> None:
    big = "x" * 5000
    blocks = [Heading(text="CHƯƠNG MỘT", level=1, page=1)]
    blocks += [Paragraph(text=big, page=1) for _ in range(10)]
    chapters, _images, _nav = _blocks_to_chapters(_doc(), blocks, max_file_bytes=10_000)
    assert len(chapters) >= 4
    assert chapters[0].title == "CHƯƠNG MỘT"
    assert all("(tiếp)" in c.title for c in chapters[1:])


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
