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

import pymupdf as fitz
from ebooklib import epub

from . import PIPELINE_VERSION
from .convert import convert_pdf
from .detect import DetectConfig, scan_ocr_book_signal
from .extract import extract_document, sha256_file

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


def _load_prior(out_dir: Path) -> dict[str, PackBook]:
    mpath = out_dir / "manifest.json"
    if not mpath.exists():
        return {}
    data = json.loads(mpath.read_text(encoding="utf-8"))
    prior: dict[str, PackBook] = {}
    for b in data.get("books", []):
        prior[b["bookUid"]] = PackBook(
            book_uid=b["bookUid"],
            title=b["title"],
            author=b["author"],
            file=b["file"],
            sha256=b["sha256"],
            pipeline_version=b["pipelineVersion"],
            source_pdf_name=b["sourcePdfName"],
        )
    return prior


def _is_scan_ocr(pdf: Path, config: DetectConfig) -> bool:
    """Tín hiệu ``scan_ocr`` **y hệt** ``convert_pdf`` (``convert.py:165``): trích bằng
    :func:`extract_document` rồi gọi :func:`scan_ocr_book_signal` với cùng ``config.detect``.

    Dùng chung đúng hàm/đúng đối số với ``convert.py`` để ``pack`` và ``convert`` luôn phân loại
    giống nhau — ``pack`` không OCR sách mà ``convert`` sẽ không đọc cache (và ngược lại).
    """
    fitz_doc = fitz.open(str(pdf))
    try:
        doc_model = extract_document(fitz_doc, pdf, config)
    finally:
        fitz_doc.close()
    n_pages = len(doc_model.pages)
    full_image = sum(1 for p in doc_model.pages if p.has_full_page_image)
    texty = sum(1 for p in doc_model.pages if p.char_count >= config.scan_min_chars)
    return scan_ocr_book_signal(n_pages, full_image, texty, config)


def _ensure_ocr(pdf: Path, cache_dir: Path | None) -> None:
    """OCR trước (Apple Vision) nếu ``pdf`` là sách ``scan_ocr`` (y hệt ``convert_pdf``) và
    chưa có cache hợp lệ.

    Chỉ chạy được trên macOS (extra ``ocr-mac``). Không có → cảnh báo và bỏ qua; ``convert_pdf``
    sẽ tự dùng lớp chữ ẩn v4 (ADR-009), không crash.
    """
    from .ocr_cache import DEFAULT_CACHE_DIR, OCR_ENGINE, cache_status, write_cache

    cdir = Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR
    if not _is_scan_ocr(pdf, DetectConfig()):
        return
    try:
        from .ocr_vision import engine_version, ocr_available, ocr_pdf
    except Exception:
        ocr_available = lambda: False  # noqa: E731
    if not ocr_available():
        print(
            f"CẢNH BÁO: {pdf.name} là scan_ocr nhưng không OCR được (không macOS/extra ocr-mac) → "
            "convert dùng v4.",
            file=sys.stderr,
        )
        return
    status = cache_status(cdir, sha256_file(pdf), OCR_ENGINE, engine_version())
    if status.ok:
        return
    write_cache(ocr_pdf(pdf), cdir)


def pack_pdfs(
    pdf_dir: str | Path,
    out_dir: str | Path,
    *,
    font_profile: str | None = None,
    engine: str = "auto",
    run_check: bool = True,
    size_warn_bytes: int = SIZE_WARN_BYTES,
    ocr_cache_dir: str | Path | None = None,
) -> PackManifest:
    pdf_dir = Path(pdf_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(ocr_cache_dir) if ocr_cache_dir is not None else None

    prior = _load_prior(out_dir)
    books: list[PackBook] = []
    for pdf in sorted(pdf_dir.glob("*.pdf")):
        pdf_sha = sha256_file(pdf)
        book_uid = f"sepia:{pdf_sha}"
        epub_path = out_dir / f"{pdf_sha}.epub"
        cached = prior.get(book_uid)
        if cached and cached.pipeline_version == PIPELINE_VERSION and epub_path.exists():
            books.append(dataclasses.replace(cached, source_pdf_name=pdf.name))
            continue
        _ensure_ocr(pdf, cache_dir)
        convert_pdf(
            pdf,
            epub_path,
            font_profile=font_profile,
            engine=engine,
            run_check=run_check,
            ocr_cache_dir=ocr_cache_dir,
        )
        title, author = _epub_title_author(epub_path)
        books.append(
            PackBook(
                book_uid=book_uid,
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
    _prune_orphans(out_dir, keep={b.file for b in books})
    _write_manifest(out_dir, manifest)
    _warn_size(out_dir, size_warn_bytes)
    return manifest


def _prune_orphans(out_dir: Path, keep: set[str]) -> None:
    """Xoá .epub trong out_dir không còn trong manifest (PDF nguồn bị xoá/đổi) để gói
    không lẫn sách cũ và không phình APK. Chỉ đụng .epub; manifest.json giữ nguyên."""
    for epub_file in out_dir.glob("*.epub"):
        if epub_file.name not in keep:
            epub_file.unlink()


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
