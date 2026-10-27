"""``pack`` — đóng gói nhiều PDF thành content pack (EPUB + manifest.json).

Tất định: chạy lại trên cùng đầu vào → EPUB & manifest y hệt (convert byte-deterministic,
books sắp theo bookUid, JSON sort_keys). Sách có bản quyền KHÔNG vào git — pack luôn nằm
ở thư mục ngoài repo hoặc content/ (gitignored).
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

from ebooklib import epub

from . import PIPELINE_VERSION
from .convert import convert_pdf
from .extract import sha256_file

PACK_VERSION = 1
SIZE_WARN_BYTES = 150 * 1024 * 1024


@dataclasses.dataclass(frozen=True)
class PackBook:
    book_uid: str
    title: str
    author: str
    file: str
    sha256: str
    pipeline_version: int
    source_pdf_name: str

    def to_dict(self) -> dict:
        return {
            "bookUid": self.book_uid,
            "title": self.title,
            "author": self.author,
            "file": self.file,
            "sha256": self.sha256,
            "pipelineVersion": self.pipeline_version,
            "sourcePdfName": self.source_pdf_name,
        }


@dataclasses.dataclass(frozen=True)
class PackManifest:
    pack_version: int
    books: tuple[PackBook, ...]

    def to_dict(self) -> dict:
        return {"packVersion": self.pack_version, "books": [b.to_dict() for b in self.books]}


def _epub_title_author(epub_path: Path) -> tuple[str, str]:
    book = epub.read_epub(str(epub_path))
    titles = book.get_metadata("DC", "title")
    authors = book.get_metadata("DC", "creator")
    title = titles[0][0] if titles else epub_path.stem
    author = authors[0][0] if authors else ""
    return title, author


def pack_pdfs(
    pdf_dir: str | Path,
    out_dir: str | Path,
    *,
    font_profile: str | None = None,
    engine: str = "auto",
    run_check: bool = True,
    size_warn_bytes: int = SIZE_WARN_BYTES,
) -> PackManifest:
    pdf_dir = Path(pdf_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    books: list[PackBook] = []
    for pdf in sorted(pdf_dir.glob("*.pdf")):
        pdf_sha = sha256_file(pdf)
        epub_path = out_dir / f"{pdf_sha}.epub"
        convert_pdf(pdf, epub_path, font_profile=font_profile, engine=engine, run_check=run_check)
        title, author = _epub_title_author(epub_path)
        books.append(
            PackBook(
                book_uid=f"sepia:{pdf_sha}",
                title=title,
                author=author,
                file=epub_path.name,
                sha256=sha256_file(epub_path),
                pipeline_version=PIPELINE_VERSION,
                source_pdf_name=pdf.name,
            )
        )

    books.sort(key=lambda b: b.book_uid)
    manifest = PackManifest(pack_version=PACK_VERSION, books=tuple(books))
    _write_manifest(out_dir, manifest)
    _warn_size(out_dir, size_warn_bytes)
    return manifest


def _write_manifest(out_dir: Path, manifest: PackManifest) -> None:
    text = json.dumps(manifest.to_dict(), ensure_ascii=False, sort_keys=True, indent=2)
    (out_dir / "manifest.json").write_text(text + "\n", encoding="utf-8")


def _warn_size(out_dir: Path, size_warn_bytes: int) -> None:
    total = sum(f.stat().st_size for f in out_dir.glob("*.epub"))
    if total > size_warn_bytes:
        print(
            f"CẢNH BÁO: pack {total / 1024 / 1024:.0f} MB > "
            f"{size_warn_bytes / 1024 / 1024:.0f} MB (Play ~200 MB; cân nhắc Play Asset Delivery).",
            file=sys.stderr,
        )
