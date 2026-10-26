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
from .model import Block, Document, Heading, ImageBlock, Paragraph, Table

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
        "figcaption { font-size: 0.9em; font-style: italic; }\n"
        "table { border-collapse: collapse; margin: 1em 0; }\n"
        "td { border: 1px solid #999; padding: 2px 6px; vertical-align: top; }\n"
    )


# Chia file: chỉ tách theo heading cấp cao **xuất hiện ít** (≤ _MAX_FORCED_CHAPTERS); nếu không có
# cấp nào đủ hiếm (vd Docling gán mọi tiêu đề là cấp 1) thì chỉ cắt theo kích thước. Nav vẫn giữ
# heading tới cấp _NAV_MAX_LEVEL làm mục (anchor trong file) → tránh hàng trăm file.
_MAX_FILE_BYTES = 100_000
_MAX_FORCED_CHAPTERS = 40
_NAV_MAX_LEVEL = 2

# Ảnh: ảnh chụp/scan → JPEG q80, cạnh dài ≤ _IMG_MAX_EDGE; ảnh ít màu (≤ _IMG_PALETTE_MAX màu) giữ
# PNG. Bỏ ảnh tí hon (cạnh < _IMG_MIN_EDGE px). (Thiếu Pillow → giữ PNG nguyên, không resize/bỏ.)
_IMG_MAX_EDGE = 1200
_IMG_JPEG_QUALITY = 80
_IMG_MIN_EDGE = 64
_IMG_PALETTE_MAX = 256


@dataclass(frozen=True)
class _Chapter:
    title: str
    file_name: str
    html_body: str


@dataclass(frozen=True)
class _NavEntry:
    file_name: str
    anchor: str
    text: str
    level: int


@dataclass(frozen=True)
class EpubReport:
    path: str
    book_uid: str
    n_chapters: int
    n_images: int


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _process_image(png: bytes) -> tuple[bytes, str, str] | None:
    """Nén/đổi cỡ ảnh → ``(bytes, ext, media_type)`` hoặc ``None`` nếu bỏ (ảnh tí hon).

    Ảnh ít màu → PNG (optimize); ảnh nhiều màu (chụp/scan) → JPEG q80. Cạnh dài ≤ ``_IMG_MAX_EDGE``.
    Thiếu Pillow → giữ PNG nguyên (không resize/bỏ) để đường heuristic không cần Pillow.
    """
    try:
        from PIL import Image
    except Exception:
        return png, "png", "image/png"
    import io

    try:
        img = Image.open(io.BytesIO(png))
        img.load()
    except Exception:
        return png, "png", "image/png"

    w, h = img.size
    if max(w, h) < _IMG_MIN_EDGE:
        return None  # ảnh tí hon → bỏ

    if max(w, h) > _IMG_MAX_EDGE:
        scale = _IMG_MAX_EDGE / max(w, h)
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)

    few_colors = img.convert("RGB").getcolors(maxcolors=_IMG_PALETTE_MAX) is not None
    out = io.BytesIO()
    if few_colors:
        img.save(out, format="PNG", optimize=True)
        return out.getvalue(), "png", "image/png"
    img.convert("RGB").save(out, format="JPEG", quality=_IMG_JPEG_QUALITY, optimize=True)
    return out.getvalue(), "jpg", "image/jpeg"


def _table_html(t: Table) -> str:
    rows = []
    for r in t.rows:
        cells = "".join(f"<td>{_esc(c)}</td>" for c in r)
        rows.append(f"<tr>{cells}</tr>")
    return "<table>" + "".join(rows) + "</table>"


def _block_html(b: Block, images: list[tuple[str, bytes, str]]) -> str:
    if isinstance(b, Heading):
        lvl = min(max(b.level, 1), 3)
        return f"<h{lvl}>{_esc(b.text)}</h{lvl}>"  # anchor thêm riêng trong _blocks_to_chapters
    if isinstance(b, Paragraph):
        return f"<p>{_esc(b.text)}</p>"
    if isinstance(b, Table):
        return _table_html(b)
    # ImageBlock — nén/đổi cỡ; ảnh tí hon bị bỏ (chỉ còn caption nếu có để vẫn tìm được).
    processed = _process_image(b.png)
    caption = f"<figcaption>{_esc(b.caption)}</figcaption>" if b.caption else ""
    if processed is None:
        return caption  # ảnh tí hon → bỏ ảnh, giữ chú thích (nếu có)
    data, ext, media_type = processed
    name = f"images/img_{len(images):04d}.{ext}"  # tên theo thứ tự duyệt → duy nhất + tất định
    images.append((name, data, media_type))
    alt = _esc(b.caption) if b.caption else f"Trang {b.page}"
    return f'<figure><img src="{name}" alt="{alt}"/>{caption}</figure>'


def _force_break_level(blocks: list[Block], max_forced: int) -> int:
    """Cấp heading lớn nhất để **ép tách file** sao cho tổng số mốc ≤ ``max_forced``; 0 = chỉ cắt
    theo kích thước (khi cả cấp 1 cũng quá nhiều, vd Docling gán mọi tiêu đề là cấp 1)."""
    counts = {1: 0, 2: 0, 3: 0}
    for b in blocks:
        if isinstance(b, Heading):
            counts[min(max(b.level, 1), 3)] += 1
    # Cấp (số nhỏ = cao) ĐẦU TIÊN xuất hiện trong khoảng [1, max_forced] → tách file ở đó.
    for lvl in (1, 2, 3):
        if 1 <= counts[lvl] <= max_forced:
            return lvl
    return 0


def _blocks_to_chapters(
    doc: Document,
    blocks: list[Block],
    *,
    max_file_bytes: int = _MAX_FILE_BYTES,
    max_forced: int = _MAX_FORCED_CHAPTERS,
    nav_max_level: int = _NAV_MAX_LEVEL,
) -> tuple[list[_Chapter], list[tuple[str, bytes, str]], list[_NavEntry]]:
    """Gom blocks thành file XHTML + danh sách nav.

    Tách file khi: (a) gặp heading cấp ≤ ``_force_break_level`` (mốc hiếm), hoặc (b) file vượt
    ``max_file_bytes`` (cắt tại ranh giới đoạn/ảnh/bảng). Mọi heading tới ``nav_max_level`` được
    gắn anchor + vào nav (dù không tách file) → nav giàu nhưng số file ít.
    """
    force_level = _force_break_level(blocks, max_forced)
    chapters: list[dict] = []
    images: list[tuple[str, bytes, str]] = []
    nav: list[dict] = []
    anchor_seq = 0

    def start_chapter(title: str) -> dict:
        ch: dict = {"title": title, "frags": [], "bytes": 0}
        chapters.append(ch)
        return ch

    cur: dict | None = None
    for b in blocks:
        if isinstance(b, Heading):
            lvl = min(max(b.level, 1), 3)
            if force_level and lvl <= force_level and (cur is None or cur["bytes"] > 0):
                cur = start_chapter(b.text)
            elif cur is None:
                cur = start_chapter(doc.title or "Mở đầu")
            anchor_seq += 1
            anchor = f"h{anchor_seq}"
            frag = f'<h{lvl} id="{anchor}">{_esc(b.text)}</h{lvl}>'
            cur["frags"].append(frag)
            cur["bytes"] += len(frag.encode("utf-8"))
            if lvl <= nav_max_level:
                nav.append({"ci": len(chapters) - 1, "anchor": anchor, "text": b.text, "lvl": lvl})
            continue
        if cur is None:
            cur = start_chapter(doc.title or "Mở đầu")
        elif cur["bytes"] > max_file_bytes and isinstance(b, Paragraph | ImageBlock | Table):
            cur = start_chapter(f"{cur['title']} (tiếp)")
        frag = _block_html(b, images)
        cur["frags"].append(frag)
        cur["bytes"] += len(frag.encode("utf-8"))

    out: list[_Chapter] = [
        _Chapter(
            title=ch["title"],
            file_name=f"chap_{i:04d}.xhtml",
            html_body="\n".join(ch["frags"]) or "<p></p>",
        )
        for i, ch in enumerate(chapters, start=1)
    ]
    nav_entries = [
        _NavEntry(
            file_name=out[e["ci"]].file_name,
            anchor=e["anchor"],
            text=e["text"],
            level=e["lvl"],
        )
        for e in nav
    ]
    return out, images, nav_entries


def _build_toc(nav_entries: list[_NavEntry], chapters: list[_Chapter]) -> list:
    """Nav 2 cấp: heading cấp 1 làm mục, cấp 2 làm mục con. Không có heading → mỗi file một mục."""
    if not nav_entries:
        return [epub.Link(c.file_name, c.title, c.file_name) for c in chapters]
    toc: list = []
    for e in nav_entries:
        link = epub.Link(f"{e.file_name}#{e.anchor}", e.text, f"{e.file_name}_{e.anchor}")
        if e.level <= 1 or not toc:
            toc.append([link, []])  # mục cha (kèm danh sách con)
        else:
            toc[-1][1].append(link)  # mục con của cha gần nhất
    final: list = []
    for link, kids in toc:
        final.append((link, tuple(kids)) if kids else link)
    return final


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

    chapters, images, nav_entries = _blocks_to_chapters(doc, blocks)

    for name, data, media_type in images:
        book.add_item(
            epub.EpubItem(
                uid=name.replace("/", "_").replace(".", "_"),
                file_name=name,
                media_type=media_type,
                content=data,
            )
        )

    epub_chapters = []
    for ch in chapters:
        item = epub.EpubHtml(title=ch.title, file_name=ch.file_name, lang="vi")
        # ebooklib bọc content trong template XHTML của nó → content chỉ là HTML trong <body>.
        item.content = ch.html_body
        item.add_item(style)
        book.add_item(item)
        epub_chapters.append(item)

    book.toc = _build_toc(nav_entries, chapters)
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
