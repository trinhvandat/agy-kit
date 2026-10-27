from pathlib import Path

import fitz  # PyMuPDF

from sepia_pipeline import PIPELINE_VERSION
from sepia_pipeline.extract import sha256_file
from sepia_pipeline.pack import PACK_VERSION, pack_pdfs


def _make_text_pdf(path: Path, title: str, body: str) -> None:
    doc = fitz.open()
    doc.set_metadata({"title": title, "author": "Tác giả Mẫu"})
    page = doc.new_page()
    page.insert_text((72, 72), body, fontname="helv", fontsize=14)
    doc.save(str(path))
    doc.close()


def test_pack_single_new_book(tmp_path):
    pdf_dir = tmp_path / "src"
    pdf_dir.mkdir()
    pdf = pdf_dir / "sach-mau.pdf"
    _make_text_pdf(pdf, "Sách Mẫu", "Một đoạn văn tiếng Việt đủ dài để không bị coi là scan.")
    out = tmp_path / "pack"

    manifest = pack_pdfs(pdf_dir, out, run_check=False)

    assert manifest.pack_version == PACK_VERSION
    assert len(manifest.books) == 1
    book = manifest.books[0]
    pdf_sha = sha256_file(pdf)
    assert book.book_uid == f"sepia:{pdf_sha}"
    assert book.file == f"{pdf_sha}.epub"
    assert book.source_pdf_name == "sach-mau.pdf"
    assert book.pipeline_version == PIPELINE_VERSION
    epub = out / book.file
    assert epub.exists()
    assert book.sha256 == sha256_file(epub)
    assert (out / "manifest.json").exists()


def test_pack_is_deterministic(tmp_path):
    pdf_dir = tmp_path / "src"
    pdf_dir.mkdir()
    _make_text_pdf(pdf_dir / "a.pdf", "A", "Đoạn văn tiếng Việt thứ nhất đủ dài.")
    out1 = tmp_path / "p1"
    out2 = tmp_path / "p2"
    m1 = pack_pdfs(pdf_dir, out1, run_check=False)
    pack_pdfs(pdf_dir, out2, run_check=False)
    assert (out1 / "manifest.json").read_bytes() == (out2 / "manifest.json").read_bytes()
    for b in m1.books:
        assert (out1 / b.file).read_bytes() == (out2 / b.file).read_bytes()


def test_pack_skips_unchanged(tmp_path, monkeypatch):
    pdf_dir = tmp_path / "src"
    pdf_dir.mkdir()
    _make_text_pdf(pdf_dir / "a.pdf", "A", "Đoạn văn tiếng Việt thứ nhất đủ dài.")
    out = tmp_path / "p"
    pack_pdfs(pdf_dir, out, run_check=False)

    import sepia_pipeline.pack as packmod

    calls = {"n": 0}
    real = packmod.convert_pdf

    def spy(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(packmod, "convert_pdf", spy)
    pack_pdfs(pdf_dir, out, run_check=False)
    assert calls["n"] == 0  # unchanged → no reconvert


def test_pack_books_sorted_by_uid(tmp_path):
    pdf_dir = tmp_path / "src"
    pdf_dir.mkdir()
    _make_text_pdf(pdf_dir / "z.pdf", "Z", "Nội dung Z tiếng Việt đủ dài.")
    _make_text_pdf(pdf_dir / "a.pdf", "A", "Nội dung A tiếng Việt đủ dài khác hẳn.")
    out = tmp_path / "p"
    m = pack_pdfs(pdf_dir, out, run_check=False)
    uids = [b.book_uid for b in m.books]
    assert uids == sorted(uids)
