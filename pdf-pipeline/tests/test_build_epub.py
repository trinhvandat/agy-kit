"""Test Bước 4 — build_epub.py: định danh ổn định, chia chương, đầu ra tất định, font profile."""

import zipfile
from pathlib import Path

import pytest
from ebooklib import epub

from sepia_pipeline import PIPELINE_VERSION
from sepia_pipeline.build_epub import build_epub, load_font_family
from sepia_pipeline.model import Document, Heading, ImageBlock, Paragraph

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32  # PNG giả (đủ magic) cho test


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
    assert report.n_chapters == 3  # front matter + 2 chương cấp 1
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


def test_chapters_split_by_h1(tmp_path: Path) -> None:
    out = tmp_path / "book.epub"
    build_epub(_doc(), _blocks(), out)
    book = epub.read_epub(str(out))
    htmls = [
        it
        for it in book.get_items()
        if isinstance(it, epub.EpubHtml) and it.file_name.startswith("chap_")
    ]
    assert len(htmls) == 3


def test_image_embedded(tmp_path: Path) -> None:
    out = tmp_path / "book.epub"
    build_epub(_doc(), _blocks(), out)
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert any(n.endswith("images/p0001.png") for n in names)


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
