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
