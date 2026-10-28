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
import io
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path

from ebooklib import epub
from PIL import Image

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
        "table { border-collapse: collapse; margin: 1em 0; width: 100%; table-layout: fixed; }\n"
        "tr { break-inside: avoid; }\n"
        "th, td { border: 1px solid #999; padding: 2px 5px; vertical-align: top;"
        " text-align: left; word-break: break-word; overflow-wrap: anywhere; }\n"
    )


# Chia file (v8): GỘP các mục liên tiếp vào một file tới ~_TARGET_CHARS ký tự, **tách ở ranh giới
# heading** (file luôn bắt đầu bằng heading). Ưu tiên tách ở cấp coarsest (vd h1); cấp sâu hơn chỉ
# tách khi file đã gần _MAX_CHARS. Đoạn/bảng/ảnh KHÔNG bị cắt đôi; đoạn/bảng khổng lồ vượt
# _MAX_CHARS vẫn giữ nguyên khối (cắt kích thước chỉ ở ranh giới khối kế tiếp). Mục tiêu ~40–80 file
# sách vài trăm nghìn ký tự (nhẹ khi mở trên điện thoại). Nav giữ heading tới _NAV_MAX_LEVEL.
_TARGET_CHARS = 7000  # vượt ngưỡng này → tách ở heading coarsest kế tiếp
_MAX_CHARS = 10_000  # trần cứng: vượt → cắt ở ranh giới khối kế tiếp (kể cả giữa chương)
_NAV_MAX_LEVEL = 3  # v10 (toc_hierarchy): nav tới 3 cấp (chương → mục đánh số → gạch đầu dòng)

# Ảnh: ảnh chụp/scan → JPEG q80, cạnh dài ≤ _IMG_MAX_EDGE; ảnh ít màu (≤ _IMG_PALETTE_MAX màu) giữ
# PNG. Bỏ ảnh tí hon (cạnh < _IMG_MIN_EDGE px). Pillow là dependency runtime bắt buộc.
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


def _attr(text: str) -> str:
    """Escape cho **giá trị thuộc tính** (có cả dấu nháy) — tránh vỡ thẻ, vd alt chứa `"`."""
    return html.escape(text, quote=True)


def _process_image(png: bytes) -> tuple[bytes, str, str] | None:
    """Nén/đổi cỡ ảnh → ``(bytes, ext, media_type)`` hoặc ``None`` nếu bỏ (ảnh tí hon).

    Ảnh ít màu → PNG (optimize); ảnh nhiều màu (chụp/scan) → JPEG q80. Cạnh dài ≤ ``_IMG_MAX_EDGE``.
    Ảnh không mở/giải mã được (bytes hỏng) → giữ PNG nguyên.
    """
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


# Bảng từ ``_TABLE_CARD_MIN_COLS`` cột trở lên: hàng đầu coi là tiêu đề, mỗi ô thân mang
# ``data-label`` (tên cột) + ``<table class="wide">`` để **app** (SepiaTheme) hiện dạng "thẻ" trên
# màn hẹp. Bảng ít cột hơn giữ nguyên dạng cũ (đã vừa màn hình). Xem docs/03 §8 Việc 4 (issue #20).
_TABLE_CARD_MIN_COLS = 4


def _table_html(t: Table) -> str:
    if not t.rows:
        return ""
    n_cols = max(len(r) for r in t.rows)
    if n_cols < _TABLE_CARD_MIN_COLS:
        rows = ["<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in r) + "</tr>" for r in t.rows]
        return "<table>" + "".join(rows) + "</table>"
    # Bảng rộng: hàng đầu = <thead>; ô thân gắn data-label từ tên cột (dạng thẻ trên màn hẹp).
    header = t.rows[0]
    thead = "<thead><tr>" + "".join(f"<th>{_esc(c)}</th>" for c in header) + "</tr></thead>"
    body_rows = []
    for r in t.rows[1:]:
        cells = "".join(
            (
                f'<td data-label="{_attr(header[i])}">{_esc(c)}</td>'
                if i < len(header) and header[i]
                else f"<td>{_esc(c)}</td>"
            )
            for i, c in enumerate(r)
        )
        body_rows.append(f"<tr>{cells}</tr>")
    return f'<table class="wide">{thead}<tbody>' + "".join(body_rows) + "</tbody></table>"


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
    if processed is None:
        # ảnh tí hon → bỏ ảnh; giữ chú thích dạng <p> (figcaption trần ngoài <figure> là HTML lỗi).
        return f"<p>{_esc(b.caption)}</p>" if b.caption else ""
    caption = f"<figcaption>{_esc(b.caption)}</figcaption>" if b.caption else ""
    data, ext, media_type = processed
    name = f"images/img_{len(images):04d}.{ext}"  # tên theo thứ tự duyệt → duy nhất + tất định
    images.append((name, data, media_type))
    alt = _attr(b.caption) if b.caption else f"Trang {b.page}"
    return f'<figure><img src="{name}" alt="{alt}"/>{caption}</figure>'


def _content_len(b: Block) -> int:
    """Số **ký tự nội dung** của một khối (để chia file theo ~ký tự, không theo byte/tag HTML)."""
    if isinstance(b, Table):
        return sum(len(c) for row in b.rows for c in row)
    if isinstance(b, ImageBlock):
        return len(b.caption or "")
    return len(getattr(b, "text", "") or "")


def _coarsest_level(blocks: list[Block]) -> int:
    """Cấp heading cao nhất (số nhỏ nhất) xuất hiện trong ``blocks``; 0 nếu không có heading."""
    levels = {min(max(b.level, 1), 3) for b in blocks if isinstance(b, Heading)}
    return min(levels) if levels else 0


def _blocks_to_chapters(
    doc: Document,
    blocks: list[Block],
    *,
    target_chars: int = _TARGET_CHARS,
    max_chars: int = _MAX_CHARS,
    nav_max_level: int = _NAV_MAX_LEVEL,
) -> tuple[list[_Chapter], list[tuple[str, bytes, str]], list[_NavEntry]]:
    """Gom blocks thành file XHTML + danh sách nav (v8 — chia nhỏ theo ~ký tự).

    - **Tách ở heading**: khi gặp heading mà file hiện tại đã có nội dung và đạt ngưỡng → mở file
      mới bắt đầu bằng heading đó. Ngưỡng theo cấp: cấp **coarsest** (vd h1) dùng ``target_chars``
      (tách sớm); cấp sâu hơn dùng ``max_chars`` (chỉ khi đã gần trần — "cấp 2 nếu còn lớn").
    - **Cắt theo kích thước**: nếu file vượt ``max_chars`` → cắt ở ranh giới khối (đoạn/ảnh/bảng) kế
      tiếp, file mới "(tiếp)". KHÔNG cắt đôi đoạn/bảng; khối khổng lồ vẫn nguyên.
    - Không bỏ mồ côi heading (file luôn có nội dung trước khi cắt kích thước).
    - Mọi heading tới ``nav_max_level`` có anchor + vào nav (dù không tách file).
    """
    coarsest = _coarsest_level(blocks)
    chapters: list[dict] = []
    images: list[tuple[str, bytes, str]] = []
    nav: list[dict] = []
    anchor_seq = 0

    def start_chapter(title: str) -> dict:
        ch: dict = {"title": title, "frags": [], "chars": 0, "has_content": False}
        chapters.append(ch)
        return ch

    cur: dict | None = None
    for b in blocks:
        if isinstance(b, Heading):
            lvl = min(max(b.level, 1), 3)
            # Cấp coarsest tách sớm (target); cấp sâu hơn chỉ tách khi gần trần (max).
            threshold = target_chars if lvl <= coarsest else max_chars
            # File mới (tên theo heading) khi: chưa có file nào, hoặc file hiện tại đã đủ ngưỡng.
            if cur is None or (cur["has_content"] and cur["chars"] >= threshold):
                cur = start_chapter(b.text)
            anchor_seq += 1
            anchor = f"h{anchor_seq}"
            frag = f'<h{lvl} id="{anchor}">{_esc(b.text)}</h{lvl}>'
            cur["frags"].append(frag)
            cur["chars"] += _content_len(b)
            # v10: chỉ đưa vào nav khi heading KHỚP mục lục in sẵn (``in_nav``); heading không khớp
            # vẫn render <hN> trong thân bài nhưng KHÔNG vào nav (tránh nav phẳng 715 mục).
            if getattr(b, "in_nav", True) and lvl <= nav_max_level:
                nav.append({"ci": len(chapters) - 1, "anchor": anchor, "text": b.text, "lvl": lvl})
            continue
        if cur is None:
            cur = start_chapter(doc.title or "Mở đầu")
        elif cur["has_content"] and cur["chars"] >= max_chars:
            cur = start_chapter(f"{cur['title']} (tiếp)")
        frag = _block_html(b, images)
        cur["frags"].append(frag)
        cur["chars"] += _content_len(b)
        cur["has_content"] = True

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
    """Nav **3 cấp lồng nhau** (v10): cấp 1 → cấp 2 → cấp 3. Không có heading → mỗi file một mục.

    Mục con bám vào cha gần nhất ở cấp trên. Mục con mồ côi (chưa có cha) được nâng lên làm cha.
    """
    if not nav_entries:
        return [epub.Link(c.file_name, c.title, c.file_name) for c in chapters]

    def mk(e: _NavEntry) -> epub.Link:
        return epub.Link(f"{e.file_name}#{e.anchor}", e.text, f"{e.file_name}_{e.anchor}")

    roots: list[list] = []  # [link, children]
    cur1: list | None = None
    cur2: list | None = None
    for e in nav_entries:
        node: list = [mk(e), []]
        if e.level <= 1 or cur1 is None:
            roots.append(node)
            cur1, cur2 = node, None
        elif e.level == 2 or cur2 is None:
            cur1[1].append(node)
            cur2 = node
        else:  # cấp 3
            cur2[1].append(node)

    def finalize(node: list):
        link, kids = node
        return link if not kids else (link, tuple(finalize(k) for k in kids))

    return [finalize(r) for r in roots]


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
