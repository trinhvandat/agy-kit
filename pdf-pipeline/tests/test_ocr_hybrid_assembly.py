"""Test dựng blocks route hybrid — **chống rò lớp chữ ABBYY** (fix-hybrid-abbyy-leak).

Thuần, KHÔNG cần docling/Vision: dựng ``order_items`` giả + cache giả, gọi thẳng
:func:`_assemble_blocks` / :func:`_assign_lines` / :func:`_insert_floating`.

Bất biến (ADR-009, SPIKE-5 v5.1):
- Trang CÓ cache: khối chữ chỉ lấy chữ Vision; khối không có dòng Vision → BỎ (không lấy ABBYY);
  picture không có chữ Vision → ảnh KHÔNG caption. → mọi từ khối chữ ⊆ chữ cache của chính trang đó.
- Trang KHÔNG cache (fallback): giữ lớp chữ Docling/ABBYY như v4.
- Mỗi dòng cache được dùng ĐÚNG MỘT lần (không mất, không lặp) — kể cả dòng "trôi".
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from sepia_pipeline.model import Heading, Paragraph
from sepia_pipeline.ocr_cache import OcrLine
from sepia_pipeline.ocr_hybrid import (
    _assemble_blocks,
    _assign_lines,
    _insert_floating,
    _Target,
)

_BB = (0.1, 0.1, 0.4, 0.15)  # bbox dòng/khối bất kỳ (không quan trọng cho dựng block)


class _FakeItem:
    """Giả item Docling: chỉ cần ``.text`` (lớp chữ ABBYY) + ``get_image`` cho picture."""

    def __init__(self, text: str = "", image: Image.Image | None = None):
        self.text = text
        self._image = image

    def get_image(self, doc):  # chữ ký như docling item
        return self._image


def _entry(label: str, page: int, *, abbyy: str = "", lines=None, image=None, bbox=_BB):
    item = _FakeItem(text=abbyy, image=image)
    t = _Target(0, page, label if label != "_floating" else "text", bbox, 0, item)
    if lines:
        t.lines = list(lines)
    return {"item": item, "label": label, "page": page, "bbox": bbox, "target": t}


def _png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (4, 4), (200, 200, 200)).save(buf, format="PNG")
    return buf.getvalue()


# --- item 1: trang CÓ cache dùng Vision, không rò ABBYY -----------------------


def test_cached_page_uses_vision_not_abbyy() -> None:
    e = _entry(
        "text",
        1,
        abbyy="RÁC abbyy nhiéu",
        lines=[OcrLine("alpha", _BB, 0.9), OcrLine("beta", _BB, 0.8)],
    )
    blocks, dropped = _assemble_blocks([e], doc=None, cached_pages={0})
    assert dropped == 0
    assert [type(b).__name__ for b in blocks] == ["Paragraph"]
    assert blocks[0].text == "alpha beta"  # chữ Vision, KHÔNG phải ABBYY


def test_cached_page_empty_text_block_dropped_and_counted() -> None:
    e = _entry("text", 1, abbyy="nhiéu điéu vđi")  # ABBYY leak, KHÔNG có dòng Vision
    blocks, dropped = _assemble_blocks([e], doc=None, cached_pages={0})
    assert blocks == []  # khối bị bỏ, KHÔNG xuất ABBYY
    assert dropped == 1


def test_cached_heading_empty_dropped() -> None:
    e = _entry("section_header", 1, abbyy="PHƯƠNG ABBYY")
    blocks, dropped = _assemble_blocks([e], doc=None, cached_pages={0})
    assert blocks == []
    assert dropped == 1


def test_fallback_page_keeps_abbyy() -> None:
    # Trang 2 (index 1) KHÔNG trong cache → fallback giữ lớp chữ ABBYY như v4.
    e = _entry("text", 2, abbyy="chữ abbyy thật")
    blocks, dropped = _assemble_blocks([e], doc=None, cached_pages={0})
    assert dropped == 0
    assert [b.text for b in blocks] == ["chữ abbyy thật"]


def test_cached_picture_no_vision_text_has_no_abbyy_caption() -> None:
    e = _entry("picture", 1, abbyy="caption abbyy rò", image=Image.new("RGB", (4, 4)))
    blocks, dropped = _assemble_blocks([e], doc=None, cached_pages={0})
    assert [type(b).__name__ for b in blocks] == ["ImageBlock"]
    assert blocks[0].caption == ""  # KHÔNG lấy caption ABBYY trên trang có cache


def test_cached_picture_with_enough_vision_text_becomes_paragraph() -> None:
    long_vi = " ".join(["chữ"] * 40)  # ≥ 80 ký tự không trắng
    e = _entry("picture", 1, lines=[OcrLine(long_vi, _BB, 0.9)], image=Image.new("RGB", (4, 4)))
    blocks, _ = _assemble_blocks([e], doc=None, cached_pages={0})
    assert [type(b).__name__ for b in blocks] == ["Paragraph"]


# --- item 2: dòng trôi KHÔNG gán vào khối gần nhất; gom thành đoạn riêng -------


def test_floating_line_not_assigned_to_nearest_block() -> None:
    a = _Target(0, 1, "text", (0.0, 0.0, 0.45, 0.5), 0, None)
    b = _Target(1, 1, "text", (0.55, 0.0, 1.0, 0.5), 0, None)
    lines = {0: [OcrLine("troi", (0.1, 0.80, 0.2, 0.85), 0.7)]}  # dưới cả hai → trôi
    assigned, cross, floating_by_page = _assign_lines([a, b], lines)
    assert assigned == 0
    assert a.lines == [] and b.lines == []  # KHÔNG bị nhét vào khối gần nhất
    assert floating_by_page == {1: [lines[0][0]]}  # trả riêng theo trang (1-based Docling)


def test_insert_floating_makes_separate_paragraph_on_cached_page() -> None:
    para = _entry("text", 1, lines=[OcrLine("trong khoi", _BB, 0.9)])
    floating = {1: [OcrLine("dong troi", (0.1, 0.9, 0.3, 0.95), 0.7)]}
    merged, n_float = _insert_floating([para], floating)
    assert n_float == 1
    blocks, _ = _assemble_blocks(merged, doc=None, cached_pages={0})
    texts = [b.text for b in blocks if isinstance(b, Paragraph)]
    assert "trong khoi" in texts
    assert "dong troi" in texts  # dòng trôi thành đoạn riêng, KHÔNG dính vào "trong khoi"


def test_insert_floating_positions_group_by_y() -> None:
    top = _entry(
        "text", 1, lines=[OcrLine("tren", (0.1, 0.1, 0.3, 0.15), 0.9)], bbox=(0.1, 0.1, 0.3, 0.15)
    )
    bot = _entry(
        "text", 1, lines=[OcrLine("duoi", (0.1, 0.7, 0.3, 0.75), 0.9)], bbox=(0.1, 0.7, 0.3, 0.75)
    )
    floating = {1: [OcrLine("giua", (0.1, 0.4, 0.3, 0.45), 0.7)]}
    merged, _ = _insert_floating([top, bot], floating)
    blocks, _ = _assemble_blocks(merged, doc=None, cached_pages={0})
    assert [b.text for b in blocks] == ["tren", "giua", "duoi"]  # chèn theo y


# --- item 3: bất biến tổng hợp -------------------------------------------------


def test_invariant_every_cache_line_used_once() -> None:
    """Mỗi dòng cache xuất hiện ĐÚNG một lần trong output (khối hoặc đoạn trôi)."""
    a = _Target(0, 1, "text", (0.0, 0.0, 1.0, 0.3), 0, _FakeItem())
    lines = {
        0: [
            OcrLine("w1", (0.1, 0.05, 0.3, 0.1), 0.9),  # trong a
            OcrLine("w2", (0.1, 0.9, 0.3, 0.95), 0.7),  # trôi
        ]
    }
    assigned, _cross, floating_by_page = _assign_lines([a], lines)
    entry = {"item": a.item, "label": "text", "page": 1, "bbox": a.bbox, "target": a}
    merged, _ = _insert_floating([entry], floating_by_page)
    blocks, _ = _assemble_blocks(merged, doc=None, cached_pages={0})
    out_words = " ".join(b.text for b in blocks if isinstance(b, Heading | Paragraph)).split()
    assert sorted(out_words) == ["w1", "w2"]  # không mất, không lặp
