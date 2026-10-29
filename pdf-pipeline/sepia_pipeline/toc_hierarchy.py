"""Bước 2c — Gán **cấp + nhãn nav cho heading theo mục lục in sẵn** (PIPELINE_VERSION 11, #20).

Vấn đề: route Vision-OCR cho ra **mọi heading cùng một cỡ chữ** → mục lục app **phẳng**. v10 khớp
TỪNG heading với mục lục nên lần nhắc tên chương trong lời giới thiệu + tiêu đề loạt lặp đều thành
mục cấp 1 → nav đầu sách đầy mục rỗng/trùng. Sách có **mục lục in sẵn** mang cấu trúc thật. Module:

1. Nhận diện **vùng mục lục in sẵn** (sau khối "MỤC LỤC", cho tới khi vào thân bài).
2. :func:`parse_chapters` — rút danh sách **chương** (dòng 'Chương/Phần/Chapter/Part N'; tên = các
   khối in hoa ngay sau marker — OCR hay tách rời) + mục con của từng chương.
3. :func:`assign_heading_levels` — **cấp 1 = chương**: mỗi chương neo đúng MỘT heading thân bài
   (lần SAU vùng mục lục, không phải lần nhắc trong lời giới thiệu; không thấy heading tên chương →
   neo vào mục con đầu). Nhãn nav = 'Chương N: <tên>' lấy CHỮ mục lục in sẵn (:class:`Heading`
   ``nav_label`` — dấu đúng hơn OCR in hoa; **KHÔNG đổi** ``text`` thân bài). Mục con khớp mục lục →
   cấp 2/3 (khử trùng trong mỗi chương). Heading không khớp (kể cả tiêu đề loạt lặp) → ngoài nav.
4. So khớp bỏ dấu + bỏ dấu câu (:func:`match_key`) để chịu OCR đổi ',' → '.'. Không có mục lục in
   sẵn → giữ nguyên blocks (fallback) + cảnh báo.

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
class Chapter:
    """Một **chương** rút từ mục lục in sẵn (dòng 'Chương/Phần/Chapter/Part N')."""

    number: int  # số chương (arabic hoặc đã quy từ số La Mã)
    marker: str  # chữ marker gốc, vd 'Chương 1' (dùng dựng nhãn nav)
    title: str  # tên chương (các khối in hoa ngay sau marker)
    children: tuple[TocEntry, ...] = ()  # mục con (cấp 2/3) để fallback neo khi thiếu heading tên

    @property
    def label(self) -> str:
        """Nhãn hiển thị trong nav: 'Chương N: <tên>' (hoặc chỉ marker nếu không có tên)."""
        return f"{self.marker}: {self.title}" if self.title else self.marker


@dataclass(frozen=True)
class TocHierarchyReport:
    """Kết quả gán cấp: blocks mới + số liệu để đo + cảnh báo chương không neo được."""

    blocks: list[Block]
    found_printed_toc: bool
    n_chapters: int  # số chương rút từ mục lục in sẵn
    anchored_chapters: int  # số chương neo được vào thân bài (qua tên hoặc mục con đầu)
    level_counts: dict[int, int]  # cấp → số heading trong nav ở cấp đó
    chapter_labels: tuple[str, ...]  # nhãn cấp 1 theo thứ tự sách (để soát)
    warnings: tuple[str, ...]  # chương neo qua mục con / không neo được / nhãn trùng


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


_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def match_key(s: str) -> str:
    """Khoá so khớp heading↔mục lục: như :func:`canon` nhưng bỏ MỌI dấu câu bên trong (., : ; …).

    OCR hay đổi ',' thành '.' hoặc rơi dấu hai chấm giữa tiêu đề in hoa (vd 'ĐAU ĐẦU. NÓNG' vs
    'ĐAU ĐẦU, NÓNG') → so bằng ``canon`` sẽ trượt. Bỏ dấu câu + gộp khoảng trắng để khớp bền hơn.
    """
    s = _PUNCT_RE.sub(" ", canon(s))
    return _WS_RE.sub(" ", s).strip()


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


# --- Rút CHƯƠNG (cấp 1) từ mục lục in sẵn ------------------------------------
_CHUONG_NUM_RE = re.compile(r"^\s*(chương|phần|chapter|part)\s+([0-9ivxlcdm]+)\b", re.IGNORECASE)
_ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def _parse_num(tok: str) -> int | None:
    """Số chương: arabic ('1') hoặc La Mã ('IV'); None nếu không đọc được."""
    if tok.isdigit():
        return int(tok)
    tok = tok.lower()
    if not tok or any(c not in _ROMAN for c in tok):
        return None
    total, prev = 0, 0
    for c in reversed(tok):
        v = _ROMAN[c]
        total += -v if v < prev else v
        prev = max(prev, v)
    return total or None


def _is_title_part(text: str) -> bool:
    """Khối có phải mảnh TÊN chương (in hoa, đứng ngay sau marker 'Chương N') không.

    Loại khối bắt đầu bằng số thứ tự / gạch đầu dòng / cột số trang / có dấu dẫn / marker khác.
    """
    t = text.strip()
    if not t or _ONLY_PAGENUMS_RE.match(t) or _LEAD_PAGE_RE.match(t):
        return False
    if _NUM_RE.match(t) or _BULLET_RE.match(t) or _LEADER_RE.search(t) or _CHUONG_NUM_RE.match(t):
        return False
    return _is_caps_title(t)


def parse_chapters(region_blocks: list[Block]) -> list[Chapter]:
    """Rút danh sách **chương** theo thứ tự từ vùng mục lục in sẵn.

    Mỗi 'Chương/Phần/Chapter/Part N' là một chương; tên = các khối in hoa ngay sau marker (OCR hay
    tách marker và tên thành hai khối). Các mục đánh số/gạch đầu dòng sau đó (tới chương kế) là
    **mục con** của chương — giữ lại để fallback neo khi không thấy heading tên chương trong thân.
    Khối TRƯỚC chương đầu (lời nói đầu, tiêu đề loạt) KHÔNG thuộc chương nào → bỏ.
    """
    texts = [_text_of(b).strip() for b in region_blocks]
    chapters: list[dict] = []
    i, n = 0, len(texts)
    while i < n:
        m = _CHUONG_NUM_RE.match(texts[i])
        num = _parse_num(m.group(2)) if m else None
        if m and num is not None:
            marker = texts[i][m.start() : m.end()].strip()
            rest = texts[i][m.end() :].strip(" :.-–—")
            parts = [rest] if _is_caps_title(rest) else []
            j = i + 1
            while j < n and _is_title_part(texts[j]):
                parts.append(texts[j])
                j += 1
            title = _strip_page_and_leaders(" ".join(p for p in parts if p))
            chapters.append({"number": num, "marker": marker, "title": title, "children": []})
            i = j
            continue
        if chapters:  # mục con của chương hiện tại (bỏ khối trước chương đầu)
            for seg in _split_inline_entries(texts[i]):
                _classify_segment(seg, chapters[-1]["children"])
        i += 1
    return [
        Chapter(
            number=c["number"], marker=c["marker"], title=c["title"], children=tuple(c["children"])
        )
        for c in chapters
    ]


# --- Khớp heading thân bài với mục lục ----------------------------------------
def _matches(key: str, target: str) -> bool:
    """``match_key`` khớp: bằng nhau, hoặc chuỗi ngắn (đủ dài) nằm trọn trong chuỗi kia."""
    if not key or not target:
        return False
    if key == target:
        return True
    short, long = (key, target) if len(key) <= len(target) else (target, key)
    return len(short) >= 10 and short in long


def _anchor_chapters(
    chapters: list[Chapter], body: list[tuple[int, str]], region_end: int
) -> tuple[list[int | None], list[bool]]:
    """Neo mỗi chương vào MỘT heading thân bài (chỉ số khối). Trả (anchors, anchored_via_child).

    Pass 1 — khớp theo TÊN chương: lấy heading SAU vùng mục lục khớp tên, lần xuất hiện ĐẦU (tức
    điểm vào chương thật, trước mọi mục con của nó — không phải lần nhắc trong lời giới thiệu vì các
    lần đó nằm trong/ trước vùng mục lục). Neo tăng dần theo thứ tự chương.
    Pass 2 — fallback: chương không thấy heading tên → neo vào heading của **mục con đầu tiên** (tìm
    trong khoảng giữa chương trước và chương sau đã neo).
    """
    anchors: list[int | None] = [None] * len(chapters)
    via_child: list[bool] = [False] * len(chapters)
    used: set[int] = set()
    lower = region_end
    for ci, ch in enumerate(chapters):
        ck = match_key(ch.title)
        if not ck:
            continue
        hit = next(
            (idx for idx, hk in body if idx >= lower and idx not in used and _matches(hk, ck)),
            None,
        )
        if hit is not None:
            anchors[ci], lower = hit, hit + 1
            used.add(hit)
    for ci, ch in enumerate(chapters):
        if anchors[ci] is not None:
            continue
        prev = max(
            (anchors[k] for k in range(ci) if anchors[k] is not None), default=region_end - 1
        )
        nxt = min(
            (anchors[k] for k in range(ci + 1, len(chapters)) if anchors[k] is not None),
            default=10**9,
        )
        for child in ch.children:
            ck = match_key(child.title)
            if len(ck) < 3:
                continue
            hit = next(
                (i for i, hk in body if prev < i < nxt and i not in used and _matches(hk, ck)), None
            )
            if hit is not None:
                anchors[ci], via_child[ci] = hit, True
                used.add(hit)
                break
    return anchors, via_child


# --- Gán cấp cho heading thân bài ---------------------------------------------
def assign_heading_levels(blocks: list[Block]) -> TocHierarchyReport:
    """Đặt cấp + nhãn nav cho heading theo mục lục in sẵn (PIPELINE_VERSION 11).

    Cấp 1 = các **chương** của mục lục in sẵn, mỗi chương neo đúng MỘT heading thân bài + nhãn
    'Chương N: <tên>' lấy từ mục lục (dấu đúng hơn OCR). Mục con khớp mục lục → cấp 2/3 trong nav.
    Heading không khớp (kể cả tiêu đề loạt/lần nhắc lặp) → cấp sâu nhất + NGOÀI nav. KHÔNG sửa
    ``text`` thân bài (immutable: dùng ``dataclasses.replace``, chỉ đổi level/in_nav/nav_label).
    """
    region = find_toc_region(blocks)
    if region is None:
        return TocHierarchyReport(
            blocks=blocks,
            found_printed_toc=False,
            n_chapters=0,
            anchored_chapters=0,
            level_counts={},
            chapter_labels=(),
            warnings=("toc-hierarchy: KHÔNG thấy mục lục in sẵn → giữ cấp heading theo cỡ chữ",),
        )
    region_blocks = blocks[region[0] : region[1]]
    chapters = parse_chapters(region_blocks)
    region_end = region[1]
    body = [
        (i, match_key(b.text))
        for i, b in enumerate(blocks)
        if isinstance(b, Heading) and i >= region_end
    ]
    anchors, via_child = _anchor_chapters(chapters, body, region_end)

    # Chỉ số neo → chương; và khoảng [neo_ci, neo_kế) để gán mục con đúng chương.
    anchor_idx = {a: ci for ci, a in enumerate(anchors) if a is not None}
    ordered = sorted(a for a in anchors if a is not None)
    next_of = {
        a: (ordered[k + 1] if k + 1 < len(ordered) else len(blocks)) for k, a in enumerate(ordered)
    }
    # Mục con mong đợi của từng chương (match_key → TocEntry), lần đầu thắng.
    want: list[dict[str, TocEntry]] = []
    for ch in chapters:
        w: dict[str, TocEntry] = {}
        for e in ch.children:
            k = match_key(e.title)
            if len(k) >= 3 and k not in w:
                w[k] = e
        want.append(w)

    out: list[Block] = []
    level_counts = {1: 0, 2: 0, 3: 0}
    consumed: list[set[str]] = [set() for _ in chapters]
    cur_ci: int | None = None
    cur_end = -1
    for i, b in enumerate(blocks):
        if not isinstance(b, Heading):
            out.append(b)
            continue
        if i in anchor_idx:  # heading neo chương → cấp 1
            ci = anchor_idx[i]
            cur_ci, cur_end = ci, next_of[i]
            level_counts[1] += 1
            out.append(dataclasses.replace(b, level=1, in_nav=True, nav_label=chapters[ci].label))
            continue
        if cur_ci is not None and i < cur_end:  # trong thân một chương → thử làm mục con
            hk = match_key(b.text)
            hit = next(
                (k for k in want[cur_ci] if k not in consumed[cur_ci] and _matches(hk, k)), None
            )
            if hit is not None:
                consumed[cur_ci].add(hit)
                e = want[cur_ci][hit]
                lvl = min(max(e.level, 2), MAX_LEVEL)
                level_counts[lvl] += 1
                out.append(dataclasses.replace(b, level=lvl, in_nav=True, nav_label=e.title))
                continue
        out.append(dataclasses.replace(b, level=MAX_LEVEL, in_nav=False, nav_label=None))

    warnings = _chapter_warnings(chapters, anchors, via_child)
    labels = tuple(chapters[ci].label for ci in sorted(anchor_idx.values()))
    return TocHierarchyReport(
        blocks=out,
        found_printed_toc=True,
        n_chapters=len(chapters),
        anchored_chapters=sum(1 for a in anchors if a is not None),
        level_counts=level_counts,
        chapter_labels=labels,
        warnings=warnings,
    )


def _chapter_warnings(
    chapters: list[Chapter], anchors: list[int | None], via_child: list[bool]
) -> tuple[str, ...]:
    out: list[str] = []
    for ci, ch in enumerate(chapters):
        if anchors[ci] is None:
            out.append(f"  {ch.label}: KHÔNG neo được vào thân bài → bỏ khỏi nav")
        elif via_child[ci]:
            out.append(f"  {ch.label}: không thấy heading tên chương → neo vào mục con đầu")
    seen: dict[str, str] = {}
    for ci, ch in enumerate(chapters):
        if anchors[ci] is None:
            continue
        key = match_key(ch.title)
        if key and key in seen:
            out.append(f"  nhãn cấp 1 TRÙNG: {ch.label!r} ~ {seen[key]!r} (2 chương trùng tên?)")
        elif key:
            seen[key] = ch.label
    return tuple(out)
