"""Bước 2 — Reflow (US-A4): bỏ header/footer/số trang, **ghép dòng thành đoạn**, giữ trang ảnh.

Hàm thuần trên mô hình :mod:`model` (không đụng PyMuPDF). Nguyên tắc (docs/03 §6):

- **KHÔNG** de-hyphenation (tiếng Việt viết rời âm tiết) — chỉ ghép dòng, không "chữa" gạch nối.
- Header/footer/số trang: dòng nằm trong dải mép trên/dưới, **lặp lại** (sau khi bỏ chữ số) trên
  ≥ ``repeat_min_fraction`` số trang → bỏ; dòng chỉ gồm số / "- 12 -" / "Trang 12" ở mép → bỏ.
- Ghép dòng: nối dòng sau vào đoạn trừ khi dòng trước kết thúc bằng dấu kết câu, HOẶC khoảng cách
  dọc lớn bất thường, HOẶC dòng sau thụt đầu dòng rõ rệt. Đoạn vắt qua hai trang vẫn nối được.
- Nhiều cột: chỉ **phát hiện + cảnh báo**, không cố tách.
"""

from __future__ import annotations

import dataclasses
import re
import statistics
import unicodedata
from collections import Counter
from dataclasses import dataclass

from . import toc
from .model import Block, Document, Heading, ImageBlock, Line, Paragraph, Table
from .vietnamese import vietnamese_score


@dataclass(frozen=True)
class ReflowConfig:
    """Ngưỡng reflow (chỉnh được; mặc định hiệu chỉnh theo sách thật ở SPIKE-4).

    - ``band_ratio``: dải mép trên/dưới = tỷ lệ này của chiều cao trang (header/footer nằm ở đây).
    - ``repeat_min_fraction``: header/footer phải lặp trên ≥ tỷ lệ này số trang mới bị bỏ.
    - ``repeat_min_pages``: tối thiểu bấy nhiêu trang mới bật phát hiện lặp (sách quá ngắn thì bỏ).
    - ``image_page_max_chars``: trang ảnh phủ kín + ít hơn bấy nhiêu ký tự thân bài → trang ảnh.
    - ``para_gap_factor``: cách dọc hai dòng > ``factor × khoảng dòng thường`` → ngắt đoạn.
    - ``indent_tolerance``: dòng sau thụt vào > bấy nhiêu pt so với mép trái đoạn → ngắt đoạn.
    - ``multicolumn_min_lines``: mỗi cột cần ≥ bấy nhiêu dòng mới tính là bố cục nhiều cột.
    """

    band_ratio: float = 0.08
    repeat_min_fraction: float = 0.30
    repeat_min_pages: int = 4
    image_page_max_chars: int = 30
    para_gap_factor: float = 1.6
    indent_tolerance: float = 14.0
    multicolumn_min_lines: int = 4
    toc_run_min: int = 3  # ≥ bấy nhiêu mục-lục-in-sẵn liên tiếp mới bỏ (tránh bỏ nhầm dòng lẻ)
    # Trang có ≥ ``toc_page_fraction`` khối (đoạn/bảng) là mục lục in sẵn VÀ ≥ 2 khối như vậy → bỏ
    # cả cụm (khớp "trang có ≥ 60% dòng dạng đó", issue #20 Việc 2): bắt mục lục rải rác không liên
    # tiếp mà run_min bỏ sót. Blob mục lục gộp (≥ 2 dãy chấm dẫn trong một khối) bỏ riêng (không cần
    # run/trang) — xem :func:`drop_printed_toc`.
    toc_page_fraction: float = 0.5
    # Tiêu đề thật ngắn: ≤ bấy nhiêu dòng liên tiếp cùng cấp. Nhiều hơn (vd lời giới thiệu in chữ
    # to nhiều dòng) → coi là ĐOẠN VĂN, không phải chuỗi heading.
    max_heading_lines: int = 2
    # Lọc dòng rác theo âm tiết Việt: khối chữ có tỷ lệ âm tiết hợp lệ < ngưỡng VÀ ngắn (heading
    # hoặc ≤ ``garbage_short_max_chars`` ký tự) → bỏ; khối dài điểm thấp → GIỮ nhưng cảnh báo.
    garbage_vn_threshold: float = 0.5
    garbage_short_max_chars: int = 60
    # Header chạy đầu trang (đường Docling): nội dung (sau chuẩn hoá, GIỮ số) trùng ở ≥ bấy nhiêu
    # trang → giữ lần đầu, bỏ các lần sau. Chỉ xét khối nằm trong dải mép trên (``top_ratio`` ≤
    # ``band_ratio``) để không bỏ nhầm nhãn mục giữa trang.
    running_header_min_pages: int = 3
    # TẮT MẶC ĐỊNH (SPIKE-4 v4): trên sách tra cứu mẫu (Đông y), Docling đặt header chạy thật
    # ("CẠO GIÓ BẢO VỆ SỨC KHỎE", top_ratio≈0.10) **cùng dải dọc** với heading mục thật và nhãn
    # "LẤY HUYỆT"/"Tên gọi:" (0.10–0.17) — KHÔNG trong dải mép trên 0.08. Thêm điều kiện bbox thì
    # không còn header nào bị bỏ (removed=0); nới ngưỡng sẽ bỏ nhầm heading thật. Theo chủ trương
    # "không chồng thêm heuristic", để bước này **tắt mặc định**; bật khi có sách header nằm sát
    # mép trên thật sự. Xem docs/spikes/spike-4-docling.md §v4.
    drop_running_headers_enabled: bool = False


# Dấu kết câu (docs/03 §6). Các ký tự đóng (ngoặc/nháy) được "trong suốt": bỏ ở cuối rồi mới xét.
_SENTENCE_ENDERS = frozenset(".!?…:")
_TRAILING_CLOSERS = "”’\"')]》»"
_PAGE_NUMBER_RE = re.compile(
    r"""^\s*
        (?:[-–—]\s*)?            # "- 12"
        (?:(?:trang|page|tr\.?|p\.?)\s*)?  # "Trang 12" / "Page 12"
        [0-9ivxlcdm]+            # số Ả Rập hoặc số La Mã
        \s*(?:[-–—])?\s*$        # "12 -"
    """,
    re.IGNORECASE | re.VERBOSE,
)


def collapse_ws(text: str) -> str:
    """Gộp khoảng trắng liên tiếp thành một dấu cách, bỏ đầu/cuối (không đụng ký tự khác)."""
    return re.sub(r"\s+", " ", text).strip()


def normalize_text(text: str) -> str:
    """NFC + gộp khoảng trắng — dùng cho text xuất ra EPUB (nhất quán re-anchor, docs/04 §3.1)."""
    return unicodedata.normalize("NFC", collapse_ws(text))


def ends_sentence(text: str) -> bool:
    """True nếu ``text`` kết thúc bằng dấu kết câu (bỏ qua ngoặc/nháy đóng ở cuối)."""
    s = text.rstrip()
    while s and s[-1] in _TRAILING_CLOSERS:
        s = s[:-1].rstrip()
    return bool(s) and s[-1] in _SENTENCE_ENDERS


def is_page_number_line(text: str) -> bool:
    """Dòng chỉ gồm số trang: "12", "- 12 -", "Trang 12", "Page 12" (chỉ xét khi ở mép trang)."""
    return bool(_PAGE_NUMBER_RE.match(text.strip()))


# --- Phát hiện header/footer lặp ----------------------------------------------


def _band_key(text: str) -> str:
    """Khoá so khớp header/footer: bỏ chữ số, gộp khoảng trắng, hạ thường (header đổi số trang)."""
    no_digits = re.sub(r"\d+", "", text)
    return collapse_ws(no_digits).lower()


def _in_top_band(line: Line, page_height: float, ratio: float) -> bool:
    return line.y0 < page_height * ratio


def _in_bottom_band(line: Line, page_height: float, ratio: float) -> bool:
    return line.y1 > page_height * (1 - ratio)


def _in_band(line: Line, page_height: float, ratio: float) -> bool:
    return _in_top_band(line, page_height, ratio) or _in_bottom_band(line, page_height, ratio)


def find_repeating_bands(doc: Document, config: ReflowConfig) -> set[str]:
    """Khoá text (``_band_key``) có trong dải mép ≥ ``repeat_min_fraction`` số trang chữ.

    Chỉ xét trang chữ (bỏ trang ảnh). Sách quá ít trang (< ``repeat_min_pages``) → trả rỗng (không
    đủ bằng chứng để coi là header lặp).
    """
    text_pages = [p for p in doc.pages if not is_image_page(p, config)]
    n = len(text_pages)
    if n < config.repeat_min_pages:
        return set()
    counter: Counter[str] = Counter()
    for page in text_pages:
        keys = {
            _band_key(ln.text)
            for ln in page.lines
            if _in_band(ln, page.height, config.band_ratio) and _band_key(ln.text)
        }
        counter.update(keys)
    threshold = config.repeat_min_fraction * n
    return {key for key, count in counter.items() if count >= threshold}


def is_image_page(page, config: ReflowConfig) -> bool:
    """Trang ảnh (US-A6): ảnh phủ kín **và** rất ít chữ thân bài."""
    return page.has_full_page_image and page.char_count < config.image_page_max_chars


def strip_running_heads(page, repeating: set[str], config: ReflowConfig) -> list[Line]:
    """Bỏ dòng header/footer lặp + dòng số trang trong dải mép. Giữ nguyên thứ tự còn lại."""
    kept: list[Line] = []
    for ln in page.lines:
        in_band = _in_band(ln, page.height, config.band_ratio)
        if in_band and (_band_key(ln.text) in repeating or is_page_number_line(ln.text)):
            continue
        kept.append(ln)
    return kept


# --- Phát hiện nhiều cột (chỉ cảnh báo) ---------------------------------------


def looks_multicolumn(lines: list[Line], page_width: float, config: ReflowConfig) -> bool:
    """Heuristic thô: có hai nhóm dòng ở nửa trái và nửa phải, mỗi nhóm đủ nhiều dòng."""
    mid = page_width / 2
    left = sum(1 for ln in lines if ln.x0 < mid * 0.85 and ln.char_count)
    right = sum(1 for ln in lines if ln.x0 > mid * 1.05 and ln.char_count)
    return left >= config.multicolumn_min_lines and right >= config.multicolumn_min_lines


# --- Ghép dòng thành đoạn ------------------------------------------------------


def _median_line_gap(lines: list[Line]) -> float:
    gaps = [
        b.y0 - a.y1
        for a, b in zip(lines, lines[1:], strict=False)
        if b.page == a.page and b.y0 >= a.y1
    ]
    pos = [g for g in gaps if g >= 0]
    return statistics.median(pos) if pos else 0.0


def _should_break(
    prev: Line, cur: Line, para_left: float, gap: float, config: ReflowConfig
) -> bool:
    """Có bắt đầu đoạn mới trước ``cur`` không (``prev`` là dòng cuối của đoạn đang gom)."""
    if ends_sentence(prev.text):
        return True
    # Thụt đầu dòng rõ rệt so với mép trái đoạn → đoạn mới.
    if cur.x0 > para_left + config.indent_tolerance:
        return True
    # Khoảng cách dọc bất thường — chỉ xét khi cùng trang (khác trang không so được).
    if cur.page == prev.page and gap > 0:
        vgap = cur.y0 - prev.y1
        if vgap > gap * config.para_gap_factor:
            return True
    return False


def build_blocks(doc: Document, config: ReflowConfig | None = None) -> list[Block]:
    """Dựng danh sách khối ngữ nghĩa (Heading/Paragraph/ImageBlock) theo thứ tự đọc.

    Đoạn văn **vắt qua trang** được nối (chỉ xét dấu câu + thụt dòng khi đổi trang). Trang ảnh chèn
    đúng vị trí trong dòng chảy. Dòng cỡ lớn liên tiếp cùng cấp được gom: ≤ ``max_heading_lines``
    dòng và đủ ngắn → một Heading; nhiều/dài hơn (lời giới thiệu in chữ to) → một Paragraph.
    """
    config = config or ReflowConfig()
    toc_config = toc.TocConfig()
    repeating = find_repeating_bands(doc, config)

    # Cỡ thân bài + cấp heading tính trên toàn bộ dòng chữ (đã bỏ header/footer).
    all_text_lines: list[Line] = []
    for page in doc.pages:
        if not is_image_page(page, config):
            all_text_lines.extend(strip_running_heads(page, repeating, config))
    body = toc.body_size(all_text_lines, toc_config)
    levels = toc.heading_size_levels(all_text_lines, body, toc_config)

    blocks: list[Block] = []
    para_lines: list[Line] = []
    head_run: list[Line] = []
    head_level = 0

    def flush_para() -> None:
        if para_lines:
            text = normalize_text(" ".join(ln.text for ln in para_lines))
            if text and re.search(r"\w", text):  # bỏ đoạn chỉ gồm ký hiệu/khoảng trắng
                blocks.append(Paragraph(text=text, page=para_lines[0].page))
            para_lines.clear()

    def flush_head_run() -> None:
        nonlocal head_level
        if not head_run:
            return
        text = normalize_text(" ".join(ln.text for ln in head_run))
        non_space = sum(1 for ch in text if not ch.isspace())
        if len(head_run) <= config.max_heading_lines and non_space <= toc_config.heading_max_chars:
            blocks.append(Heading(text=text, level=head_level, page=head_run[0].page))
        elif re.search(r"\w", text):
            # Quá nhiều dòng / quá dài để là tiêu đề → đoạn văn chữ to (lời giới thiệu…).
            blocks.append(Paragraph(text=text, page=head_run[0].page))
        head_run.clear()
        head_level = 0

    for page in doc.pages:
        if is_image_page(page, config):
            flush_para()
            flush_head_run()
            if page.image_png is not None:
                blocks.append(ImageBlock(png=page.image_png, page=page.number))
            continue

        kept = strip_running_heads(page, repeating, config)
        gap = _median_line_gap(kept)
        for ln in kept:
            lvl = toc.heading_level(ln, body, levels, toc_config)
            if lvl is not None:
                flush_para()
                if head_run and lvl == head_level:
                    head_run.append(ln)
                else:
                    flush_head_run()
                    head_run.append(ln)
                    head_level = lvl
                continue
            flush_head_run()
            # Bỏ dòng chỉ gồm ký hiệu (vd "•", "»") — trang trí, không phải thân bài.
            if not re.search(r"\w", ln.text):
                continue
            if para_lines:
                para_left = min(x.x0 for x in para_lines)
                if _should_break(para_lines[-1], ln, para_left, gap, config):
                    flush_para()
            para_lines.append(ln)

    flush_para()
    flush_head_run()
    return blocks


# --- Bỏ trang/khối mục lục in sẵn (áp cho cả hai engine) ----------------------

# Dòng mục lục in sẵn: có **dấu dẫn** VÀ kết thúc bằng số trang. Dấu dẫn = ≥4 dấu chấm, ký tự `…`,
# HOẶC gạch dưới `_` (OCR thường đọc dãy chấm dẫn mảnh thành `_`, vd "Đôi nét về lịch sử Đông y _
# 22"). Bare `_` là mẫu lỏng nhưng được chặn kép: (a) phải có số trang cuối dòng, (b) chỉ bỏ khi
# thành **chuỗi ≥ toc_run_min khối liên tiếp** (xem :func:`drop_printed_toc`).
_TOC_ENTRY_RE = re.compile(r"(\.\s*){4,}|…|_")
_TRAILING_NUM_RE = re.compile(r"\d+\s*$")


def _is_toc_entry_text(text: str) -> bool:
    return bool(_TOC_ENTRY_RE.search(text) and _TRAILING_NUM_RE.search(text))


# Dấu gạch đầu mục OCR sai: trên sách mẫu, MỌI "»"/"®" là ký hiệu gạch đầu mục (◦/▪) bị OCR đọc sai
# — đứng đầu dòng, sau "• " của list_item, hoặc giữa đoạn do ghép dòng. Nhận diện khi dấu **đứng
# riêng** (đầu chuỗi hoặc có khoảng trắng phía trước) → đổi thành "• ". KHÔNG đụng "»" dính liền chữ
# phía trước (vd nháy đóng «…»: "nội dung»") để giữ đúng khi sách khác dùng « » làm dấu nháy thật.
_BULLET_MARK_RE = re.compile(r"(?:^|(?<=\s))[»®]\s*")
_MULTI_BULLET_RE = re.compile(r"(?:•\s*){2,}")


def tidy_bullet_markers(blocks: list[Block]) -> list[Block]:
    """Đổi dấu `»`/`®` (gạch đầu mục OCR sai) thành `• ` trong Heading/Paragraph.

    Trả danh sách mới (immutable).

    Chỉ đổi dấu **đứng riêng** (xem khối chú thích trên); gộp "• •" nhân đôi về một "• ". `»`/`®`
    dính liền chữ (nghi nháy đóng) giữ nguyên. Xem docs/03 §8, issue #20 Việc 3.
    """
    out: list[Block] = []
    for b in blocks:
        if isinstance(b, Heading | Paragraph) and ("»" in b.text or "®" in b.text):
            t = _BULLET_MARK_RE.sub("• ", b.text)
            t = _MULTI_BULLET_RE.sub("• ", t)  # "• • X" → "• X"
            t = collapse_ws(t)
            out.append(dataclasses.replace(b, text=t))
        else:
            out.append(b)
    return out


def _block_is_toc(block: Block) -> tuple[bool, int]:
    """(có phải mục lục in sẵn, số dòng mục lục) cho một khối."""
    if isinstance(block, Paragraph):
        return (_is_toc_entry_text(block.text), 1)
    if isinstance(block, Table):
        rows = [" ".join(r) for r in block.rows]
        toc_rows = sum(1 for r in rows if _is_toc_entry_text(r))
        return (bool(rows) and toc_rows / len(rows) >= 0.5, len(block.rows))
    return (False, 0)


# Blob mục lục gộp: một đoạn chứa ≥ 2 **dãy chấm dẫn** (`....`/`…`) → chắc chắn là mục lục dồn nhiều
# mục (OCR/Docling gộp cả trang mục lục thành một khối). Chấm dẫn dày không xuất hiện trong văn
# xuôi.
_DOT_LEADER_RE = re.compile(r"\.{4,}|…")


def _toc_marker_count(text: str) -> int:
    return len(_DOT_LEADER_RE.findall(text))


# "Mạnh" = chắc chắn là mục lục dù đứng một mình: có dãy ≥ 6 chấm (không hề có trong văn xuôi), HOẶC
# kết thúc bằng **dấu dẫn `_`/`…` + số trang** (vd "… 132", "_ 142", "_174"). Dạng sau bắt cả
# mục lục
# bị Docling gán nhầm thành Heading (ngưỡng mật độ/chuỗi bỏ sót vì không đếm Heading). An toàn: tiêu
# đề chương thật không kết thúc bằng "_<số>"/"…<số>" (đã xác minh có bản heading sạch song song).
_STRONG_TOC_RE = re.compile(r"\.{6,}|[_…]\s*\d+\s*$")


def _is_strong_toc(text: str) -> bool:
    return bool(_STRONG_TOC_RE.search(text))


def drop_printed_toc(
    blocks: list[Block], config: ReflowConfig | None = None
) -> tuple[list[Block], int]:
    """Bỏ **mục lục in sẵn** (dòng chấm/gạch-dưới-dẫn + số trang) khỏi nội dung.

    Ba cơ chế bổ trợ (một khối trúng bất kỳ cái nào → bỏ):
    1. **Blob gộp**: đoạn chứa ≥ 2 dãy chấm dẫn → mục lục dồn nhiều mục trong một khối.
    2. **Chuỗi liên tiếp**: ≥ ``toc_run_min`` khối mục lục kề nhau (một bảng mục lục tính luôn).
    3. **Mật độ trang**: trang có ≥ 2 khối (đoạn/bảng) mục lục VÀ chiếm ≥ ``toc_page_fraction`` số
       khối đoạn/bảng của trang → bỏ cả cụm (bắt mục lục rải rác không liên tiếp).

    Trả ``(blocks_còn_lại, số_dòng_mục_lục_đã_bỏ)``.
    """
    config = config or ReflowConfig()
    flags = [_block_is_toc(b) for b in blocks]
    is_toc = [f[0] for f in flags]
    drop = [False] * len(blocks)

    # 1) Blob gộp (≥ 2 dãy chấm dẫn) hoặc mục lục "mạnh" (≥6 chấm / kết thúc "_|…<số>") — bỏ dù đứng
    #    một mình, áp cho cả Heading (mục lục bị gán nhầm heading).
    for k, b in enumerate(blocks):
        text = getattr(b, "text", "")
        if isinstance(b, Paragraph) and _toc_marker_count(text) >= 2:
            drop[k] = True
        elif isinstance(b, Heading | Paragraph) and _is_strong_toc(text):
            drop[k] = True

    # 2) Chuỗi liên tiếp ≥ toc_run_min (hoặc có bảng mục lục trong chuỗi).
    i = 0
    while i < len(blocks):
        if is_toc[i]:
            j = i
            while j < len(blocks) and is_toc[j]:
                j += 1
            if (j - i) >= config.toc_run_min or any(
                isinstance(blocks[k], Table) for k in range(i, j)
            ):
                for k in range(i, j):
                    drop[k] = True
            i = j
        else:
            i += 1

    # 3) Mật độ trang: trang mục-lục-dày → bỏ mọi khối mục lục trên trang đó.
    page_text_idx: dict[int, list[int]] = {}
    for k, b in enumerate(blocks):
        if isinstance(b, Paragraph | Table):
            page_text_idx.setdefault(getattr(b, "page", 0), []).append(k)
    for idxs in page_text_idx.values():
        toc_idxs = [k for k in idxs if is_toc[k]]
        if len(toc_idxs) >= 2 and len(toc_idxs) / len(idxs) >= config.toc_page_fraction:
            for k in toc_idxs:
                drop[k] = True

    removed = sum(flags[k][1] for k in range(len(blocks)) if drop[k])
    kept = [b for b, d in zip(blocks, drop, strict=True) if not d]
    return kept, removed


# --- Lọc dòng rác (âm tiết Việt) — áp cho cả hai engine ----------------------


def _non_space_len(text: str) -> int:
    return sum(1 for ch in text if not ch.isspace())


@dataclass(frozen=True)
class GarbageFilterResult:
    """Kết quả lọc rác: khối giữ lại, text khối đã bỏ (ví dụ để báo cáo), khối dài điểm thấp."""

    kept: list[Block]
    removed: tuple[str, ...]  # text các khối rác ngắn đã bỏ
    long_low_score: tuple[str, ...]  # khối DÀI điểm thấp: GIỮ nhưng cảnh báo (nghi OCR/ font hỏng)


def drop_garbage_blocks(
    blocks: list[Block], config: ReflowConfig | None = None
) -> GarbageFilterResult:
    """Bỏ **khối chữ rác** (tỷ lệ âm tiết Việt hợp lệ thấp) — chỉ khi NGẮN, để không mất nội dung.

    Chỉ xét ``Heading``/``Paragraph`` (ảnh/bảng giữ nguyên). Khối điểm < ``garbage_vn_threshold``:
    - **ngắn** (heading, hoặc ≤ ``garbage_short_max_chars`` ký tự) → bỏ (rác trang trí / OCR hỏng);
    - **dài** → giữ (có thể là nội dung thật dính lỗi) nhưng ghi vào ``long_low_score`` để cảnh báo.
    """
    config = config or ReflowConfig()
    kept: list[Block] = []
    removed: list[str] = []
    long_low: list[str] = []
    for b in blocks:
        if not isinstance(b, Heading | Paragraph):
            kept.append(b)
            continue
        if vietnamese_score(b.text) >= config.garbage_vn_threshold:
            kept.append(b)
            continue
        is_short = (
            isinstance(b, Heading) or _non_space_len(b.text) <= config.garbage_short_max_chars
        )
        if is_short:
            removed.append(b.text)
        else:
            long_low.append(b.text)
            kept.append(b)
    return GarbageFilterResult(kept=kept, removed=tuple(removed), long_low_score=tuple(long_low))


# --- Bỏ header chạy đầu trang (đường Docling) --------------------------------


def _running_head_key(text: str) -> str:
    """Khoá so khớp **tiêu đề chạy đầu trang** (đường Docling): gộp khoảng trắng + hạ thường, **GIỮ
    chữ số**.

    Khác :func:`_band_key` (heuristic bỏ chữ số vì header + số trang nằm chung một dòng): Docling
    **tách số trang thành khối riêng**, nên tiêu đề chạy thật (vd "ĐÔNG Y VÀ BÍ QUYẾT DƯỠNG SINH BỐN
    MÙA") không chứa số. Giữ chữ số để "Chương 1", "Chương 2"… (heading **chương thật**, khác nhau)
    KHÔNG bị gộp cùng khoá rồi xoá nhầm — lỗi cũ khi dùng ``_band_key`` ở đây.
    """
    return collapse_ws(text).lower()


@dataclass(frozen=True)
class RunningHeaderResult:
    """Kết quả bỏ tiêu đề chạy đầu trang: khối giữ lại, số khối bỏ, danh sách header (duy nhất)."""

    kept: list[Block]
    removed: int
    examples: tuple[str, ...]  # "text (×số trang)" cho mỗi header lặp đã bỏ (giữ 1, bỏ phần dư)


def drop_running_headers(
    blocks: list[Block], config: ReflowConfig | None = None
) -> RunningHeaderResult:
    """Bỏ **tiêu đề chạy đầu trang** lặp lại (đường Docling).

    "Đầu trang" = khối **mở đầu** mỗi trang theo thứ tự đọc, nếu là ``Heading`` (hoặc khối ngắn)
    **và nằm trong dải mép trên** — ``top_ratio`` ghi được và ≤ ``band_ratio`` (tái dùng ngưỡng dải
    mép của heuristic). Điều kiện ``top_ratio`` tránh bỏ nhầm **nhãn mục thật** nằm giữa trang (vd
    "Tên gọi:", "LẤY HUYỆT" trong sách tra cứu — lặp đầu mỗi bài nhưng không ở mép trên). Khối
    **không có** ``top_ratio`` (đường heuristic) → không bao giờ là ứng viên.

    Dùng :func:`_running_head_key` (**giữ chữ số** + hạ thường) làm khoá so khớp. Khoá xuất hiện ở
    đầu trang trên ≥ ``running_header_min_pages`` trang khác nhau → **giữ lần đầu, bỏ các lần sau**.
    Trả :class:`RunningHeaderResult` — ``examples`` liệt kê header duy nhất đã bỏ + số trang (giống
    ``garbage_examples``) để người duyệt thấy đã bỏ gì.
    """
    config = config or ReflowConfig()

    def is_head_candidate(b: Block) -> bool:
        top = getattr(b, "top_ratio", None)
        if top is None or top > config.band_ratio:
            return False
        return isinstance(b, Heading) or (
            isinstance(b, Paragraph) and _non_space_len(b.text) <= config.garbage_short_max_chars
        )

    # Khối mở đầu mỗi trang (theo thứ tự đọc) + khoá của nó.
    leading_key: dict[int, str] = {}  # index khối → khoá header
    leading_text: dict[str, str] = {}  # khoá → text hiển thị (lần đầu thấy)
    seen_page: set[int] = set()
    for i, b in enumerate(blocks):
        page = getattr(b, "page", 0)
        if page in seen_page:
            continue
        seen_page.add(page)
        if is_head_candidate(b):
            text = getattr(b, "text", "")
            key = _running_head_key(text)
            if key:
                leading_key[i] = key
                leading_text.setdefault(key, text)

    counts: Counter[str] = Counter(leading_key.values())
    repeating = {k for k, n in counts.items() if n >= config.running_header_min_pages}

    kept: list[Block] = []
    first_kept: set[str] = set()
    removed = 0
    for i, b in enumerate(blocks):
        key = leading_key.get(i)
        if key is not None and key in repeating:
            if key in first_kept:
                removed += 1
                continue
            first_kept.add(key)
        kept.append(b)

    examples = tuple(f"{collapse_ws(leading_text[k])} (×{counts[k]})" for k in sorted(repeating))
    return RunningHeaderResult(kept=kept, removed=removed, examples=examples)


def collect_warnings(doc: Document, config: ReflowConfig | None = None) -> list[str]:
    """Cảnh báo chất lượng nhẹ cho reflow: trang nhiều cột, trang ảnh có ảnh nhỏ bị bỏ qua."""
    config = config or ReflowConfig()
    warnings: list[str] = []
    repeating = find_repeating_bands(doc, config)
    multicol = [
        page.number
        for page in doc.pages
        if not is_image_page(page, config)
        and looks_multicolumn(strip_running_heads(page, repeating, config), page.width, config)
    ]
    if multicol:
        warnings.append(
            f"{len(multicol)} trang nghi nhiều cột (thứ tự đọc có thể sai): "
            f"{multicol[:10]}{'…' if len(multicol) > 10 else ''}"
        )
    return warnings
