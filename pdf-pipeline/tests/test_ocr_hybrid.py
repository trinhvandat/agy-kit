"""Test route hybrid — phần hình học/gán dòng (thuần, KHÔNG cần docling/Vision).

Phần chạy Docling thật nằm ở kiểm thủ công trên sách mẫu (spike-5 doc) + importorskip khi có extra.
"""

import pytest

from sepia_pipeline.ocr_cache import OcrLine
from sepia_pipeline.ocr_hybrid import (
    FURNITURE_BAND_RATIO,
    FURNITURE_MIN_PAGES,
    _assign_lines,
    _center_dist2,
    _furniture_key,
    _norm_bbox,
    _overlap_frac,
    _Target,
    _target_text,
    detect_furniture,
    docling_available,
    extract_blocks_hybrid,
)


class _TL:
    def __init__(self, left, top, right, bot):
        self.l, self.t, self.r, self.b = left, top, right, bot


class _BBox:
    """Giả lập docling BoundingBox: to_top_left_origin trả hộp trên-trái (points)."""

    def __init__(self, tl: _TL):
        self._tl = tl

    def to_top_left_origin(self, page_height):
        return self._tl


class _Item:
    def __init__(self, bbox):
        self.prov = [type("P", (), {"bbox": bbox})()]


def test_norm_bbox_normalizes_top_left() -> None:
    item = _Item(_BBox(_TL(100, 50, 300, 90)))
    assert _norm_bbox(item, 1000, 1000) == (0.1, 0.05, 0.3, 0.09)


def test_norm_bbox_none_without_prov() -> None:
    assert _norm_bbox(type("X", (), {})(), 1000, 1000) is None


def test_overlap_frac() -> None:
    line = (0.45, 0.10, 0.55, 0.15)  # một nửa nằm trong A=(0,0,0.5,0.5)
    assert _overlap_frac(line, (0.0, 0.0, 0.5, 0.5)) == pytest.approx(0.5)
    assert _overlap_frac(line, (0.0, 0.8, 0.5, 1.0)) == 0.0  # không chạm
    assert _overlap_frac((0.1, 0.1, 0.2, 0.2), (0.0, 0.0, 0.5, 0.5)) == pytest.approx(1.0)


def test_assign_lines_overlap_cross_floating() -> None:
    a = _Target(0, 1, "text", (0.0, 0.0, 0.5, 0.5), 0, None)
    b = _Target(1, 1, "text", (0.5, 0.0, 1.0, 0.5), 0, None)
    lines = {
        0: [  # cache 0-based ↔ Docling page 1
            OcrLine("a", (0.1, 0.10, 0.4, 0.15), 0.9),  # trong A
            OcrLine("b", (0.6, 0.10, 0.9, 0.15), 0.8),  # trong B
            OcrLine("c", (0.38, 0.10, 0.56, 0.15), 0.95),  # vắt A|B (A nhiều hơn) → cross, gán A
            OcrLine("d", (0.1, 0.80, 0.2, 0.85), 0.7),  # dưới cả hai → TRÔI (không nhét vào A/B)
        ]
    }
    assigned, cross, floating_by_page = _assign_lines([a, b], lines)
    assert (assigned, cross) == (3, 1)
    assert [ln.text for ln in a.lines] == ["a", "c"]  # "d" KHÔNG còn bị nhét vào khối gần nhất
    assert [ln.text for ln in b.lines] == ["b"]
    assert floating_by_page == {1: [lines[0][3]]}  # "d" trả riêng theo trang Docling 1-based


def test_target_text_keeps_vision_order_and_min_conf() -> None:
    # GIỮ thứ tự Vision gốc (không sắp lại theo y,x) — tránh trộn cột khi khối là "picture" to.
    t = _Target(0, 1, "text", (0, 0, 1, 1), 0, None)
    t.lines = [
        OcrLine("một", (0.1, 0.10, 0.3, 0.15), 0.9),
        OcrLine("hai", (0.5, 0.10, 0.7, 0.15), 0.95),
        OcrLine("ba", (0.1, 0.80, 0.3, 0.85), 0.7),
    ]
    text, conf = _target_text(t)
    assert text == "một hai ba"  # đúng thứ tự Vision gốc
    assert conf == pytest.approx(0.7)  # min


def test_target_text_empty() -> None:
    assert _target_text(_Target(0, 1, "text", (0, 0, 1, 1), 0, None)) == ("", None)


def test_center_dist2() -> None:
    assert _center_dist2((0, 0, 0.2, 0.2), (0, 0, 0.2, 0.2)) == 0.0
    assert _center_dist2((0, 0, 0.1, 0.1), (0.9, 0.9, 1.0, 1.0)) > 1.0


@pytest.mark.skipif(docling_available(), reason="docling đã cài → không test nhánh thiếu extra")
def test_hybrid_requires_docling(tmp_path) -> None:
    from sepia_pipeline.ocr_cache import OCR_ENGINE, OCR_RENDER, OcrCache

    cache = OcrCache("sepia:x", "x", dict(OCR_RENDER), dict(OCR_ENGINE), {}, "2026-10-27")
    with pytest.raises(RuntimeError):
        extract_blocks_hybrid(tmp_path / "x.pdf", cache)


# --- Việc 1: bỏ "đồ đạc" (tiêu đề chạy / số trang) theo bbox dòng Vision ------


def _top(text: str, page: int, y0: float = 0.02) -> OcrLine:
    """Dòng nằm trong dải mép trên (ứng viên furniture)."""
    return OcrLine(text, (0.1, y0, 0.9, y0 + 0.02), 0.9)


def _mid(text: str, page: int) -> OcrLine:
    """Dòng giữa trang (thân bài / heading thật) — KHÔNG phải ứng viên furniture."""
    return OcrLine(text, (0.1, 0.4, 0.9, 0.45), 0.9)


def test_furniture_key_collapses_trailing_ocr_variants() -> None:
    # Biến thể OCR chỉ khác phần đuôi → cùng khoá (2 từ đầu, sau khi bỏ số + chữ-cái-đơn dẫn đầu).
    k = _furniture_key("Chương 5: Phương pháp chữa bệnh: Cứu mối ngải")
    assert _furniture_key("Chương 5: Phương pháp chữa bệnh: Cứu mỗi ngài") == k
    assert _furniture_key("/ Chương 5: Phương pháp chữa bệnh: Cứu mói ngỏi") == k  # bỏ "/" dẫn đầu
    assert _furniture_key("J Chương 5: Phương pháp chữa bệnh") == k  # bỏ chữ-cái-đơn "J" dẫn đầu


def test_detect_furniture_drops_repeated_top_band_header() -> None:
    # Header chạy lặp ở mép trên trên >=3 trang → bỏ; dòng thân bài giữ.
    pages = {i: [_top("TỰ HỌC ĐÔNG Y", i), _mid(f"Nội dung trang {i}", i)] for i in range(5)}
    res = detect_furniture(pages)
    assert res.removed == 5  # 5 header bị bỏ
    for i in range(5):
        assert [ln.text for ln in res.kept_by_page[i]] == [f"Nội dung trang {i}"]
    # Bất biến: giữ + bỏ = tổng
    total = sum(len(v) for v in pages.values())
    kept = sum(len(v) for v in res.kept_by_page.values())
    assert kept + res.removed == total


def test_detect_furniture_keeps_header_below_min_pages() -> None:
    # Chỉ xuất hiện 2 trang (< FURNITURE_MIN_PAGES) → GIỮ (không đủ bằng chứng là furniture).
    assert FURNITURE_MIN_PAGES == 3
    pages = {i: [_top("Lời tựa hiếm gặp", i)] for i in range(2)}
    res = detect_furniture(pages)
    assert res.removed == 0


def test_detect_furniture_keeps_real_heading_in_page_body() -> None:
    # Cùng CHỮ với header chạy nhưng nằm GIỮA trang (ngoài dải mép) → KHÔNG bỏ (heading thật còn).
    pages = {i: [_top("TỰ HỌC ĐÔNG Y", i)] for i in range(4)}
    pages[0] = [_mid("TỰ HỌC ĐÔNG Y", 0), _top("TỰ HỌC ĐÔNG Y", 0)]
    res = detect_furniture(pages)
    # Trang 0: dòng giữa trang còn, dòng mép trên bị bỏ.
    assert [ln.text for ln in res.kept_by_page[0]] == ["TỰ HỌC ĐÔNG Y"]
    assert res.kept_by_page[0][0].bbox[1] == 0.4  # đúng là dòng giữa trang


def test_detect_furniture_drops_page_numbers_in_band() -> None:
    pages = {
        i: [OcrLine("12" if i % 2 else "- 13 -", (0.45, 0.96, 0.55, 0.99), 0.9), _mid("x", i)]
        for i in range(3)
    }
    res = detect_furniture(pages)
    assert res.removed == 3  # 3 dòng số trang ở mép dưới
    assert all(len(res.kept_by_page[i]) == 1 for i in range(3))


def test_detect_furniture_examples_list_unique_with_counts() -> None:
    pages = {i: [_top("TỰ HỌC ĐÔNG Y", i)] for i in range(4)}
    res = detect_furniture(pages)
    assert len(res.examples) == 1
    assert "×4" in res.examples[0]
    assert "TỰ HỌC ĐÔNG Y" in res.examples[0]


def test_furniture_band_ratio_default() -> None:
    assert FURNITURE_BAND_RATIO == 0.08
