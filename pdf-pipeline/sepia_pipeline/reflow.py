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

import re
import statistics
import unicodedata
from collections import Counter
from dataclasses import dataclass

from . import toc
from .model import Block, Document, Heading, ImageBlock, Line, Paragraph


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
    # Tiêu đề thật ngắn: ≤ bấy nhiêu dòng liên tiếp cùng cấp. Nhiều hơn (vd lời giới thiệu in chữ
    # to nhiều dòng) → coi là ĐOẠN VĂN, không phải chuỗi heading.
    max_heading_lines: int = 2


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


def strip_running_heads(
    page, repeating: set[str], config: ReflowConfig
) -> list[Line]:
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
        if (
            len(head_run) <= config.max_heading_lines
            and non_space <= toc_config.heading_max_chars
        ):
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
