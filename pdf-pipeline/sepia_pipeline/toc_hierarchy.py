"""Bước 2c — Gán **cấp heading theo mục lục in sẵn** (PIPELINE_VERSION 10, issue #20).

Vấn đề: route Vision-OCR cho ra **mọi heading cùng một cỡ chữ** → `toc.heading_level` trả cấp 1
cho tất cả → mục lục app **phẳng** (715 mục cấp 1, vô dụng). Sách có **mục lục in sẵn** mang cấu
trúc thật (chương / mục đánh số / gạch đầu dòng). Module này:

1. Nhận diện **vùng mục lục in sẵn** (sau khối "MỤC LỤC", cho tới khi vào thân bài).
2. **Phân rã** vùng đó thành danh sách **mục** có cấp (dấu hiệu CHUNG, không gắn lĩnh vực):
   - "Chương/Phần/Chapter/Part N" hoặc dòng TOÀN HOA (tên chương) → **cấp 1**
   - đánh số "1.", "2." → **cấp 2**
   - gạch đầu dòng "•", "»", "-" → **cấp 3**
   - bỏ số trang + dấu dẫn (chấm/gạch-dưới).
3. **Khớp** từng mục với heading trong thân bài (chuẩn hoá NFC + bỏ dấu + gộp khoảng trắng, so gần
   đúng) → đặt cấp cho heading đó. Heading **không khớp** mục nào → cấp sâu nhất và **ngoài nav**.
4. Không có mục lục in sẵn → giữ nguyên blocks (fallback), gọi bên ngoài tự cảnh báo.

Thuần (chỉ phụ thuộc :mod:`.model`) → tất định, test được không cần PDF.
"""

from __future__ import annotations

import dataclasses
import re
import unicodedata
from dataclasses import dataclass

from .model import Block, Heading, Paragraph, Table

# --- Dấu hiệu cấp (chung, không gắn lĩnh vực) ---------------------------------
_CHUONG_RE = re.compile(r"^(chương|phần|chapter|part)\s+[0-9ivxlcIVXLC]+\b", re.IGNORECASE)
_NUM_RE = re.compile(r"^(\d{1,3})\s*[.)]\s+")
_BULLET_RE = re.compile(r"^[•»▪◦·‣*]\s*|^[-–—]\s+")
# Dấu dẫn (dãy chấm/gạch-dưới) + số trang cuối dòng (kể cả dải "12-13").
_LEADER_RE = re.compile(r"[.·…]{2,}|_{2,}")
# Số trang cuối dòng (kể cả dải "12-13") + dấu dẫn/rác bám quanh.
_TRAIL_PAGE_RE = re.compile(r"[\s.·…_*\-–—•»]*\d{1,4}(?:\s*[-–]\s*\d{1,4})?[\s.·…_*]*$")
_LEAD_PAGE_RE = re.compile(r"^\s*\d{1,4}\s*(?:[-–]\s*\d{1,4})?[\s.·…_]+")
_STRIP_CHARS = " .·…_-–—*•»:\t"
# Khối toàn số (cột số trang bị OCR tách riêng) — bỏ hẳn.
_ONLY_PAGENUMS_RE = re.compile(r"^[\s\d.·…_\-–]+$")

MAX_LEVEL = 3


@dataclass(frozen=True)
class TocEntry:
    """Một mục mục-lục đã phân rã: tiêu đề (đã bỏ số trang/dấu dẫn) + cấp 1..3."""

    title: str
    level: int


@dataclass(frozen=True)
class TocHierarchyReport:
    """Kết quả gán cấp: blocks mới + số liệu để đo + danh sách mục KHÔNG khớp heading nào."""

    blocks: list[Block]
    found_printed_toc: bool
    toc_entries: int
    matched_headings: int
    level_counts: dict[int, int]  # cấp → số heading được đặt vào cấp đó (có trong nav)
    unmatched_toc_titles: tuple[str, ...]  # mục lục có mà không tìm thấy heading (in để soát)


# --- Chuẩn hoá để so khớp -----------------------------------------------------
def strip_diacritics(s: str) -> str:
    """Bỏ dấu thanh/dấu phụ + đ→d (NFD, loại ký tự kết hợp)."""
    nfd = unicodedata.normalize("NFD", s)
    out = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return out.replace("đ", "d").replace("Đ", "D")


_WS_RE = re.compile(r"\s+")


def canon(s: str) -> str:
    """NFC + bỏ dấu + thường + gộp khoảng trắng + bỏ ký tự không phải chữ/số ở hai đầu."""
    s = strip_diacritics(unicodedata.normalize("NFC", s))
    s = _WS_RE.sub(" ", s).strip().lower()
    return s.strip(" .·…_-–—•»*:")


def _strip_page_and_leaders(s: str) -> str:
    s = _LEADER_RE.sub(" ", s)
    s = _LEAD_PAGE_RE.sub("", s).strip(_STRIP_CHARS)
    # Bỏ số trang cuối + dấu dẫn/rác bám quanh — lặp cho tới ổn định (vd "... y 22 ." → "... y").
    for _ in range(3):
        nxt = _TRAIL_PAGE_RE.sub("", s).strip(_STRIP_CHARS)
        if nxt == s:
            break
        s = nxt
    return _WS_RE.sub(" ", s).strip()


def _is_caps_title(s: str) -> bool:
    """Dòng (gần) TOÀN HOA — tên chương in hoa (vd 'PHƯƠNG PHÁP XOA BÓP DƯỠNG SINH')."""
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 4:
        return False
    upper = sum(1 for c in letters if c == c.upper() and c != c.lower())
    return upper / len(letters) >= 0.85


# --- Nhận diện vùng mục lục in sẵn --------------------------------------------
def _text_of(b: Block) -> str:
    if isinstance(b, (Heading, Paragraph)):
        return b.text
    if isinstance(b, Table):
        return " ".join(" ".join(r) for r in b.rows)
    return ""


def _looks_toc_line(text: str) -> bool:
    """Dòng mang 'mùi' mục lục: có dấu dẫn, hoặc bắt đầu bằng marker, hoặc kết thúc số trang."""
    t = text.strip()
    if not t:
        return False
    if _LEADER_RE.search(t) or _ONLY_PAGENUMS_RE.match(t):
        return True
    if _CHUONG_RE.match(t) or _NUM_RE.match(t) or _BULLET_RE.match(t):
        return True
    if _TRAIL_PAGE_RE.search(t) and len(t) < 160:
        return True
    if t.endswith(":") and len(t) < 120:
        return True
    return _is_caps_title(t) and len(t) < 120


def find_toc_region(blocks: list[Block]) -> tuple[int, int] | None:
    """Trả (đầu, cuối) chỉ số khối của vùng mục lục in sẵn, hoặc None nếu không có.

    Neo bằng khối chuẩn hoá == "muc luc"; gom tiếp cho tới khi gặp một dãy khối KHÔNG-mùi-TOC
    (đã vào thân bài). Chỉ xét trong ~40% số khối đầu (mục lục luôn ở đầu sách).
    """
    limit = max(30, len(blocks) * 2 // 5)
    start = None
    for i, b in enumerate(blocks[:limit]):
        if canon(_text_of(b)) in ("muc luc", "muc luc chi tiet", "muc luc sach"):
            start = i
            break
    if start is None:
        return None
    end = start + 1
    miss = 0
    for j in range(start + 1, min(len(blocks), start + 400)):
        if _looks_toc_line(_text_of(blocks[j])):
            end = j + 1
            miss = 0
        else:
            miss += 1
            if miss >= 3:  # 3 khối liền không-mùi-TOC → kết thúc vùng
                break
    return (start, end)


# --- Phân rã vùng mục lục thành các mục có cấp --------------------------------
def _split_inline_entries(text: str) -> list[str]:
    """Tách một đoạn gộp nhiều mục ('1. A .. 22 2. B .. 24') thành từng mục.

    Cắt TRƯỚC mỗi 'N. <chữ>' hoặc '• <chữ>' (marker theo sau là CHỮ — tránh cắt ở số trang '22 ..').
    """
    parts = re.split(r"(?=(?:\b\d{1,3}[.)]|[•»▪◦])\s+\S*[^\W\d_])", text)
    return [p.strip() for p in parts if p.strip()]


def parse_toc_entries(region_blocks: list[Block]) -> list[TocEntry]:
    """Phân rã các khối vùng mục lục thành danh sách [TocEntry] (tiêu đề + cấp)."""
    entries: list[TocEntry] = []
    for b in region_blocks:
        raw = _text_of(b).strip()
        if not raw or canon(raw) in ("muc luc", "muc luc chi tiet", "muc luc sach"):
            continue
        if _ONLY_PAGENUMS_RE.match(raw):
            continue  # cột số trang OCR tách riêng
        for seg in _split_inline_entries(raw):
            _classify_segment(seg, entries)
    # Gộp mục trùng tiêu đề (giữ cấp NÔNG nhất — gần gốc hơn).
    best: dict[str, int] = {}
    order: list[str] = []
    for e in entries:
        key = canon(e.title)
        if not key or len(key) < 3:
            continue
        if key not in best:
            best[key] = e.level
            order.append(key)
        else:
            best[key] = min(best[key], e.level)
    titled = {canon(e.title): e.title for e in entries}
    return [TocEntry(title=titled[k], level=best[k]) for k in order]


def _classify_segment(seg: str, out: list[TocEntry]) -> None:
    s = seg.strip()
    if not s:
        return
    level = 2  # mặc định: mục con đánh số/không marker
    if _BULLET_RE.match(s):
        level = 3
        s = _BULLET_RE.sub("", s, count=1)
    elif _NUM_RE.match(s):
        level = 2
        s = _NUM_RE.sub("", s, count=1)
    elif _CHUONG_RE.match(s) or _is_caps_title(s) or s.endswith(":"):
        level = 1
    title = _strip_page_and_leaders(s)
    # Bỏ marker còn sót (vd "Chương 1" đứng riêng → tên chương ở khối sau sẽ là caps-title cấp 1).
    if _CHUONG_RE.match(title):
        return
    if len(canon(title)) >= 3:
        out.append(TocEntry(title=title, level=level))


# --- Gán cấp cho heading thân bài ---------------------------------------------
def assign_heading_levels(blocks: list[Block]) -> TocHierarchyReport:
    """Đặt cấp heading theo mục lục in sẵn; heading không khớp → cấp sâu nhất + ngoài nav.

    Trả [TocHierarchyReport]. KHÔNG sửa blocks tại chỗ (immutable: dùng ``dataclasses.replace``).
    """
    region = find_toc_region(blocks)
    if region is None:
        return TocHierarchyReport(
            blocks=blocks,
            found_printed_toc=False,
            toc_entries=0,
            matched_headings=0,
            level_counts={},
            unmatched_toc_titles=(),
        )
    region_blocks = blocks[region[0] : region[1]]
    entries = parse_toc_entries(region_blocks)
    level_by_canon: dict[str, int] = {canon(e.title): e.level for e in entries}

    out: list[Block] = []
    matched = 0
    matched_titles: set[str] = set()
    level_counts: dict[int, int] = {1: 0, 2: 0, 3: 0}
    for b in blocks:
        if not isinstance(b, Heading):
            out.append(b)
            continue
        key = canon(b.text)
        lvl = level_by_canon.get(key)
        if lvl is None:
            lvl = _fuzzy_level(key, level_by_canon)
        if lvl is not None:
            matched += 1
            matched_titles.add(_nearest_entry_key(key, level_by_canon))
            level_counts[lvl] = level_counts.get(lvl, 0) + 1
            out.append(dataclasses.replace(b, level=lvl, in_nav=True))
        else:
            out.append(dataclasses.replace(b, level=MAX_LEVEL, in_nav=False))

    unmatched = tuple(e.title for e in entries if canon(e.title) not in matched_titles)
    return TocHierarchyReport(
        blocks=out,
        found_printed_toc=True,
        toc_entries=len(entries),
        matched_headings=matched,
        level_counts=level_counts,
        unmatched_toc_titles=unmatched,
    )


def _fuzzy_level(key: str, level_by_canon: dict[str, int]) -> int | None:
    """Khớp gần đúng: một chuỗi chứa trọn chuỗi kia (đủ dài) → lấy cấp mục lục."""
    if len(key) < 6:
        return None
    best_lvl = None
    best_len = 0
    for ek, lvl in level_by_canon.items():
        if len(ek) < 6:
            continue
        if key == ek or (len(ek) >= 10 and (ek in key or key in ek)):
            if len(ek) > best_len:
                best_len = len(ek)
                best_lvl = lvl
    return best_lvl


def _nearest_entry_key(key: str, level_by_canon: dict[str, int]) -> str:
    if key in level_by_canon:
        return key
    for ek in level_by_canon:
        if len(ek) >= 10 and (ek in key or key in ek):
            return ek
    return key
