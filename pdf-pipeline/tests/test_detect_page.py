"""Cycle 3 — gộp span thành nhãn trang + độ phủ ảnh (hàm thuần)."""

from sepia_pipeline.detect import (
    EMPTY,
    LEGACY_TCVN3,
    LEGACY_VNI,
    MIXED,
    SCAN,
    TEXT_UNICODE,
    DetectConfig,
    classify_page,
    image_coverage,
)

CFG = DetectConfig()
VI = "Tôi yêu tiếng Việt và học thuốc Đông y mỗi ngày thật chăm chỉ"  # >30 ký tự
GARBAGE = "T«i yªu ti·ng ViÖt vµ häc thuèc §«ng y mçi ngµy th·t ch¨m"


def test_image_coverage_full_page() -> None:
    assert image_coverage([(0, 0, 100, 100)], page_area=100 * 100) == 1.0


def test_image_coverage_partial_takes_max() -> None:
    # Lấy ảnh lớn nhất: 50x50=2500 trên 10000 = 0.25
    cov = image_coverage([(0, 0, 10, 10), (0, 0, 50, 50)], page_area=100 * 100)
    assert abs(cov - 0.25) < 1e-9


def test_image_coverage_none() -> None:
    assert image_coverage([], page_area=10000) == 0.0


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


def test_tcvn3_page_by_font() -> None:
    spans = [(".VnTime", VI)]
    assert classify_page(spans, char_count=len(VI), image_coverage=0.0, config=CFG) == LEGACY_TCVN3


def test_vni_page_by_font() -> None:
    spans = [("VNI-Times", VI)]
    assert classify_page(spans, char_count=len(VI), image_coverage=0.0, config=CFG) == LEGACY_VNI


def test_mixed_unicode_and_legacy() -> None:
    # Một nửa span Unicode, một nửa span legacy (mỗi loại ≥ 15%) → mixed
    spans = [("Literata", VI), (".VnTime", VI)]
    assert classify_page(spans, char_count=len(VI) * 2, image_coverage=0.0, config=CFG) == MIXED


def test_small_legacy_noise_does_not_flip_unicode_page() -> None:
    # Trang chủ yếu Unicode + một mẩu legacy rất nhỏ (<15%) → vẫn text_unicode
    spans = [("Literata", VI * 10), (".VnTime", "abc")]
    label = classify_page(spans, char_count=len(VI) * 10 + 3, image_coverage=0.0, config=CFG)
    assert label == TEXT_UNICODE


def test_scan_takes_priority_over_text_when_few_chars() -> None:
    # Dù có vài span, nếu char_count < ngưỡng và ảnh phủ kín → scan (trang scan có chú thích nhỏ)
    spans = [("Literata", "abc")]
    assert classify_page(spans, char_count=3, image_coverage=0.9, config=CFG) == SCAN
