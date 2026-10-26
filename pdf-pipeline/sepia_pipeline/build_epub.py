"""Bước 4 — Dựng EPUB 3 bằng ebooklib (ADR-004).

Yêu cầu chính (docs/03 §8, docs/04 §6):

- ``dc:identifier`` = ``sepia:`` + SHA-256 PDF gốc → **không đổi giữa các lần build** (book_uid).
- Ghi ``PIPELINE_VERSION`` vào metadata (``<meta property="sepia:pipeline-version">``).
- Chia chương theo heading cấp 1 (không dồn cả cuốn vào một XHTML).
- CSS mặc định chỉ ``font-family: serif``; cờ ``--font-profile`` ghi tên font cụ thể (đọc từ
  ``font_profiles.toml``). **Không nhúng file font.**
- **Đầu ra tất định**: cùng PDF + cùng ``PIPELINE_VERSION`` → EPUB **giống hệt từng byte** (cố định
  ngày sửa đổi, thứ tự file trong zip, tên file ảnh, compression).
"""

from __future__ import annotations

import datetime
import html
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path

from ebooklib import epub

from . import PIPELINE_VERSION
from .model import Block, Document, Heading, ImageBlock, Paragraph

# Ngày sửa đổi cố định (EPUB yêu cầu đúng MỘT dcterms:modified — ebooklib tự ghi theo opt `mtime`).
# Cố định để đầu ra tất định.
_FIXED_MTIME = datetime.datetime(2020, 1, 1, 0, 0, 0)
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)

_FONT_PROFILES_PATH = Path(__file__).resolve().parent.parent / "font_profiles.toml"


def load_font_family(profile: str | None, path: Path | None = None) -> str:
    """Trả chuỗi ``font-family`` cho CSS. ``None`` → ``serif``; tên profile → đọc từ TOML."""
    if not profile:
        return "serif"
    toml_path = path or _FONT_PROFILES_PATH
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    profiles = data.get("profiles", {})
    if profile not in profiles:
        available = ", ".join(sorted(profiles)) or "(trống)"
        raise KeyError(f"font-profile '{profile}' không có; có sẵn: {available}")
    return profiles[profile]["font_family"]


def _css(font_family: str) -> str:
    return (
        f"body {{ font-family: {font_family}; line-height: 1.6; margin: 1em; }}\n"
        "h1, h2, h3 { line-height: 1.3; page-break-after: avoid; }\n"
        "p { margin: 0 0 0.8em; }\n"
        "img { max-width: 100%; height: auto; }\n"
        "figure { margin: 1em 0; text-align: center; }\n"
    )


@dataclass(frozen=True)
class _Chapter:
    title: str
    file_name: str
    html_body: str
    toc_subs: tuple[tuple[str, str], ...]  # (anchor, title) cho heading cấp 2


@dataclass(frozen=True)
class EpubReport:
    path: str
    book_uid: str
    n_chapters: int
    n_images: int


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _blocks_to_chapters(
    doc: Document, blocks: list[Block]
) -> tuple[list[_Chapter], list[tuple[str, bytes]]]:
    """Gom blocks thành chương (chia theo heading cấp 1). Trả (chapters, images)."""
    chapters: list[dict] = []
    images: list[tuple[str, bytes]] = []
    anchor_seq = 0

    def start_chapter(title: str) -> dict:
        ch = {"title": title, "frags": [], "subs": []}
        chapters.append(ch)
        return ch

    cur: dict | None = None
    for b in blocks:
        if isinstance(b, Heading) and b.level == 1:
            cur = start_chapter(b.text)
            cur["frags"].append(f"<h1>{_esc(b.text)}</h1>")
            continue
        if cur is None:
            cur = start_chapter(doc.title or "Mở đầu")
        if isinstance(b, Heading):
            anchor_seq += 1
            anchor = f"h{anchor_seq}"
            cur["frags"].append(f'<h{b.level} id="{anchor}">{_esc(b.text)}</h{b.level}>')
            if b.level == 2:
                cur["subs"].append((anchor, b.text))
        elif isinstance(b, Paragraph):
            cur["frags"].append(f"<p>{_esc(b.text)}</p>")
        elif isinstance(b, ImageBlock):
            name = f"images/p{b.page:04d}.png"
            images.append((name, b.png))
            cur["frags"].append(
                f'<figure><img src="{name}" alt="Trang {b.page}"/></figure>'
            )

    out: list[_Chapter] = []
    for i, ch in enumerate(chapters, start=1):
        out.append(
            _Chapter(
                title=ch["title"],
                file_name=f"chap_{i:04d}.xhtml",
                html_body="\n".join(ch["frags"]) or "<p></p>",
                toc_subs=tuple(ch["subs"]),
            )
        )
    return out, images


def _normalize_epub_zip(path: Path) -> None:
    """Viết lại zip với ngày cố định + thứ tự giữ nguyên + compression cố định → bytes tất định."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(path) as zin:
        infos = zin.infolist()
        with zipfile.ZipFile(tmp, "w") as zout:
            for info in infos:
                data = zin.read(info.filename)
                zi = zipfile.ZipInfo(info.filename, date_time=_ZIP_DATE)
                zi.external_attr = info.external_attr
                zi.create_system = info.create_system
                if info.filename == "mimetype":
                    zout.writestr(zi, data, compress_type=zipfile.ZIP_STORED)
                else:
                    zout.writestr(zi, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    tmp.replace(path)


def build_epub(
    doc: Document,
    blocks: list[Block],
    out_path: str | Path,
    *,
    font_family: str = "serif",
    pipeline_version: int = PIPELINE_VERSION,
) -> EpubReport:
    """Dựng EPUB tất định từ ``doc`` + ``blocks`` đã reflow. Trả :class:`EpubReport`."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    book = epub.EpubBook()
    book.set_identifier(doc.book_uid)  # dc:identifier ổn định (docs/04 §6)
    book.set_title(doc.title or doc.source_pdf_name)
    book.set_language("vi")
    if doc.author:
        book.add_author(doc.author)
    # Khai báo prefix `sepia:` để metadata riêng hợp lệ EPUB3 (epubcheck OPF-028).
    book.prefixes = ["sepia: https://github.com/trinhvandat/sepia/ns#"]
    # Metadata truy vết + ngày cố định (tất định).
    book.add_metadata(None, "meta", str(pipeline_version), {"property": "sepia:pipeline-version"})
    book.add_metadata(None, "meta", doc.source_pdf_name, {"property": "sepia:source-pdf"})

    style = epub.EpubItem(
        uid="style_main",
        file_name="style/main.css",
        media_type="text/css",
        content=_css(font_family).encode("utf-8"),
    )
    book.add_item(style)

    chapters, images = _blocks_to_chapters(doc, blocks)

    for name, png in images:
        book.add_item(
            epub.EpubItem(
                uid=name.replace("/", "_").replace(".", "_"),
                file_name=name,
                media_type="image/png",
                content=png,
            )
        )

    epub_chapters = []
    toc: list = []
    for ch in chapters:
        item = epub.EpubHtml(title=ch.title, file_name=ch.file_name, lang="vi")
        # ebooklib bọc content trong template XHTML của nó → content chỉ là HTML trong <body>.
        item.content = ch.html_body
        item.add_item(style)
        book.add_item(item)
        epub_chapters.append(item)
        if ch.toc_subs:
            subs = [
                epub.Link(f"{ch.file_name}#{a}", t, f"{ch.file_name}_{a}")
                for a, t in ch.toc_subs
            ]
            toc.append((epub.Link(ch.file_name, ch.title, ch.file_name), subs))
        else:
            toc.append(epub.Link(ch.file_name, ch.title, ch.file_name))

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *epub_chapters]

    # epub3_pages=False: không quét page-list (tránh lxml parse body rỗng của nav).
    # mtime cố định → dcterms:modified tất định (ebooklib tự ghi đúng một lần).
    epub.write_epub(str(out_path), book, {"epub3_pages": False, "mtime": _FIXED_MTIME})
    _normalize_epub_zip(out_path)

    return EpubReport(
        path=str(out_path),
        book_uid=doc.book_uid,
        n_chapters=len(chapters),
        n_images=len(images),
    )
