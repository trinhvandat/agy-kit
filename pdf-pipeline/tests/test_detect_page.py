"""Cycle 3 — gộp span thành nhãn trang + độ phủ ảnh (hàm thuần)."""

from sepia_pipeline.detect import (
    EMPTY,
    LEGACY_TCVN3,
    LEGACY_VNI,
    MIXED,
    SCAN,
    SCAN_OCR,
    TEXT_UNICODE,
    DetectConfig,
    PageResult,
    _aggregate,
    classify_page,
    image_coverage,
)


def _page(label: str) -> PageResult:
    return PageResult(
        page_number=1, label=label, char_count=50, image_coverage=0.0, legacy_ratio=0.0
    )

CFG = DetectConfig()
VI = "Tôi yêu tiếng Việt và học thuốc Đông y mỗi ngày thật chăm chỉ"  # >30 ký tự, có ệ/đ
GARBAGE = "T«i yªu ti·ng ViÖt vµ häc thuèc §«ng y mçi ngµy th·t ch¨m"
# Text trang font cũ "thực tế" (không có chữ Việt Unicode thật) → tên font legacy thắng.
LEGACY_TEXT = "Noi dung khong co dau tieng Viet gi dac biet o trong trang sach nay"


def test_image_coverage_full_page() -> None:
    assert image_coverage([(0, 0, 100, 100)], page_area=100 * 100) == 1.0


def test_image_coverage_nested_boxes_is_union_not_sum() -> None:
    # Ảnh nhỏ nằm trong ảnh lớn: union = 2500/10000 = 0.25 (không cộng dồn thành 0.26).
    cov = image_coverage([(0, 0, 10, 10), (0, 0, 50, 50)], page_area=100 * 100)
    assert abs(cov - 0.25) < 1e-9


def test_image_coverage_tiled_strips_sum_to_union() -> None:
    # Scan chia 2 dải ngang không chồng nhau, mỗi dải 40% → union 80% ≥ 70% → đủ để thành scan.
    strips = [(0, 0, 100, 40), (0, 40, 100, 80)]
    cov = image_coverage(strips, page_area=100 * 100)
    assert abs(cov - 0.80) < 1e-9


def test_tiled_scan_detected_as_scan() -> None:
    # Ít chữ + nhiều dải ảnh (không dải nào ≥70% một mình) → vẫn phải là scan.
    strips = [(0, 0, 100, 35), (0, 35, 100, 70), (0, 70, 100, 100)]
    cov = image_coverage(strips, page_area=100 * 100)
    assert classify_page([], char_count=2, image_coverage=cov, config=CFG) == SCAN


def test_image_coverage_none() -> None:
    assert image_coverage([], page_area=10000) == 0.0


def test_image_coverage_clamps_to_page_frame() -> None:
    # Ảnh tràn ra ngoài trang: chỉ tính phần trong khung [0,100]×[0,100] → 50..100 = 0.25.
    cov = image_coverage([(50, 50, 200, 200)], page_area=100 * 100, page_size=(100, 100))
    assert abs(cov - 0.25) < 1e-9


def test_grid_matches_exact_within_2pct() -> None:
    boxes = [(10, 10, 50, 40), (60, 20, 90, 80), (5, 60, 40, 95)]
    exact = image_coverage(boxes, page_area=100 * 100, page_size=(100, 100))
    grid = image_coverage(
        boxes, page_area=100 * 100, page_size=(100, 100),
        config=DetectConfig(image_grid_threshold=0),  # ép dùng lưới
    )
    assert abs(grid - exact) < 0.02


def test_grid_fast_on_many_images() -> None:
    import time

    boxes = [(i % 20 * 5, i // 20 * 5, i % 20 * 5 + 4, i // 20 * 5 + 4) for i in range(400)]
    start = time.perf_counter()
    cov = image_coverage(boxes, page_area=100 * 100, page_size=(100, 100))
    elapsed = time.perf_counter() - start
    assert elapsed < 0.2, f"quá chậm: {elapsed:.3f}s"
    assert 0.0 <= cov <= 1.0


def test_grid_early_stop_reaches_threshold() -> None:
    # 400 ảnh 5×5 lát kín trang; early_stop_at=0.7 → trả về ≥ 0.7 (đủ để kết luận scan).
    boxes = [(i % 20 * 5, i // 20 * 5, i % 20 * 5 + 5, i // 20 * 5 + 5) for i in range(400)]
    cov = image_coverage(
        boxes, page_area=100 * 100, page_size=(100, 100), early_stop_at=0.7
    )
    assert cov >= 0.7


def test_image_coverage_zero_page_area_safe() -> None:
    assert image_coverage([(0, 0, 10, 10)], page_area=0) == 0.0


def test_scan_page() -> None:
    # Ít chữ + ảnh phủ kín → scan
    assert classify_page([], char_count=3, image_coverage=0.95, config=CFG) == SCAN


def test_empty_page() -> None:
    # Ít chữ, không ảnh lớn → empty
    assert classify_page([], char_count=0, image_coverage=0.0, config=CFG) == EMPTY


def test_few_chars_small_image_is_empty() -> None:
    assert classify_page([], char_count=5, image_coverage=0.2, config=CFG) == EMPTY


def test_unicode_page() -> None:
    spans = [("Literata", VI)]
    assert classify_page(spans, char_count=len(VI), image_coverage=0.0, config=CFG) == TEXT_UNICODE


def test_scan_ocr_page() -> None:
    # Đủ chữ (≥ scan_min_chars) VÀ ảnh phủ kín → scan có lớp OCR.
    spans = [("Literata", VI)]
    label = classify_page(spans, char_count=len(VI), image_coverage=0.95, config=CFG)
    assert label == SCAN_OCR


def test_text_page_with_small_image_is_not_scan_ocr() -> None:
    spans = [("Literata", VI)]
    label = classify_page(spans, char_count=len(VI), image_coverage=0.2, config=CFG)
    assert label == TEXT_UNICODE


def test_tcvn3_page_by_font() -> None:
    spans = [(".VnTime", LEGACY_TEXT)]
    n = len(LEGACY_TEXT)
    assert classify_page(spans, char_count=n, image_coverage=0.0, config=CFG) == LEGACY_TCVN3


def test_vni_page_by_font() -> None:
    spans = [("VNI-Times", LEGACY_TEXT)]
    n = len(LEGACY_TEXT)
    assert classify_page(spans, char_count=n, image_coverage=0.0, config=CFG) == LEGACY_VNI


def test_mixed_unicode_and_legacy() -> None:
    # Một span Unicode thật, một span legacy theo tên font (mỗi loại ≥ 15%) → mixed
    spans = [("Literata", VI), (".VnTime", LEGACY_TEXT)]
    total = len(VI) + len(LEGACY_TEXT)
    assert classify_page(spans, char_count=total, image_coverage=0.0, config=CFG) == MIXED


def test_small_legacy_noise_does_not_flip_unicode_page() -> None:
    # Trang chủ yếu Unicode + một mẩu legacy rất nhỏ (<15%) → vẫn text_unicode
    spans = [("Literata", VI * 10), (".VnTime", "abc")]
    label = classify_page(spans, char_count=len(VI) * 10 + 3, image_coverage=0.0, config=CFG)
    assert label == TEXT_UNICODE


def test_book_majority_label_wins() -> None:
    book = _aggregate("b.pdf", [_page(TEXT_UNICODE), _page(TEXT_UNICODE), _page(LEGACY_TCVN3)])
    assert book.label == TEXT_UNICODE


def test_book_tie_prefers_actionable_legacy_over_unicode() -> None:
    # Hòa 50/50 giữa legacy và unicode → chọn nhãn "cần xử lý" (legacy), không giấu dưới unicode.
    book = _aggregate("b.pdf", [_page(TEXT_UNICODE), _page(LEGACY_TCVN3)])
    assert book.label == LEGACY_TCVN3


def test_book_tie_scan_over_scan_ocr() -> None:
    # Scan thuần (chưa có text) "cần xử lý" hơn scan đã có lớp OCR.
    book = _aggregate("b.pdf", [_page(SCAN), _page(SCAN_OCR)])
    assert book.label == SCAN


def test_book_tie_scan_ocr_over_text_unicode() -> None:
    book = _aggregate("b.pdf", [_page(SCAN_OCR), _page(TEXT_UNICODE)])
    assert book.label == SCAN_OCR


def test_book_tie_prefers_legacy_over_scan() -> None:
    book = _aggregate("b.pdf", [_page(SCAN), _page(LEGACY_VNI)])
    assert book.label == LEGACY_VNI


def test_scan_takes_priority_over_text_when_few_chars() -> None:
    # Dù có vài span, nếu char_count < ngưỡng và ảnh phủ kín → scan (trang scan có chú thích nhỏ)
    spans = [("Literata", "abc")]
    assert classify_page(spans, char_count=3, image_coverage=0.9, config=CFG) == SCAN
