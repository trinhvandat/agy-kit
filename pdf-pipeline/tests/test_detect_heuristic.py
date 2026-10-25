"""Cycle 2 — heuristic thống kê ký tự + whitelist CJK + phân loại span."""

from sepia_pipeline.detect import (
    LEGACY_OTHER,
    LEGACY_TCVN3,
    TEXT_UNICODE,
    DetectConfig,
    classify_span,
    is_cjk,
    legacy_char_ratio,
)

# Chuỗi tiếng Việt Unicode hợp lệ (có dấu precomposed) — KHÔNG được coi là legacy.
VI_UNICODE = "Tôi yêu tiếng Việt và học thuốc Đông y mỗi ngày"
# Giả lập chuỗi TCVN3 bị rút ra thành "rác": nhiều ký tự Latin-1 vùng 0x80–0xBF.
VI_TCVN3_GARBAGE = "T«i yªu ti·ng ViÖt vµ häc thuèc §«ng y"


def test_unicode_vietnamese_has_near_zero_legacy_ratio() -> None:
    assert legacy_char_ratio(VI_UNICODE) < 0.05


def test_tcvn3_garbage_has_high_legacy_ratio() -> None:
    assert legacy_char_ratio(VI_TCVN3_GARBAGE) > 0.15


def test_empty_text_ratio_is_zero() -> None:
    assert legacy_char_ratio("") == 0.0
    assert legacy_char_ratio("   \n\t ") == 0.0


def test_ascii_english_has_zero_legacy_ratio() -> None:
    assert legacy_char_ratio("The quick brown fox jumps over 12 lazy dogs.") == 0.0


def test_is_cjk_whitelist() -> None:
    assert is_cjk("一")  # U+4E00 CJK Unified
    assert is_cjk("㐀")  # U+3400 Extension A
    assert is_cjk("豈")  # U+F900 Compatibility Ideographs
    assert not is_cjk("a")
    assert not is_cjk("ô")
    assert not is_cjk("«")


def test_cjk_not_counted_as_legacy() -> None:
    # Chữ Hán chèn giữa tiếng Việt Unicode không được đẩy ratio lên.
    assert legacy_char_ratio("Huyệt 穴 ở kinh 經 lạc 絡") < 0.05


def test_classify_span_by_font_name_wins() -> None:
    # Tên font legacy thắng, kể cả khi text trông "sạch".
    assert classify_span(".VnTime", "noi dung", DetectConfig()) == LEGACY_TCVN3


def test_classify_span_heuristic_flags_renamed_font() -> None:
    # Font tên sạch nhưng text là rác legacy → legacy_other (bắt font bị đổi tên).
    assert classify_span("TimesNewRomanPSMT", VI_TCVN3_GARBAGE, DetectConfig()) == LEGACY_OTHER


def test_classify_span_clean_unicode() -> None:
    assert classify_span("Literata", VI_UNICODE, DetectConfig()) == TEXT_UNICODE


def test_threshold_is_configurable() -> None:
    low = DetectConfig(legacy_char_ratio_threshold=0.01)
    high = DetectConfig(legacy_char_ratio_threshold=0.99)
    assert classify_span("CleanFont", VI_TCVN3_GARBAGE, low) == LEGACY_OTHER
    assert classify_span("CleanFont", VI_TCVN3_GARBAGE, high) == TEXT_UNICODE


# Mis-decode "thực tế" hơn: nhiều ký tự rơi vào 0xC0–0xFF (không phải vùng 0x80–0xBF).
VI_REALISTIC_GARBAGE = (
    "Trong y häc cæ truyÒn, huyÖt vÞ lµ nh÷ng ®iÓm ®Æc biÖt trªn c¬ thÓ con ng­êi"
)
# Chữ Việt Unicode hợp lệ có đủ nguyên âm Latin-1 precomposed + Đ/đ — KHÔNG được gắn cờ.
VI_UNICODE_FULL = "Đàn bà sầu riêng ở phủ Tây Hồ, ông ấy mê mẩn cà phê đá à é ô õ ú ý"


def test_realistic_misdecode_flagged() -> None:
    # Regression cho HIGH-finding: mis-decode điển hình (nhiều ký tự 0xC0–0xFF) phải vượt ngưỡng.
    assert legacy_char_ratio(VI_REALISTIC_GARBAGE) > 0.15
    assert classify_span("CleanFont", VI_REALISTIC_GARBAGE, DetectConfig()) == LEGACY_OTHER


def test_valid_vietnamese_latin1_not_flagged() -> None:
    # Nguyên âm Việt precomposed (ÀÁÂÃÈÉÊ… à á ô õ) KHÔNG bị tính là rác.
    assert legacy_char_ratio(VI_UNICODE_FULL) < 0.05
    assert classify_span("Literata", VI_UNICODE_FULL, DetectConfig()) == TEXT_UNICODE


def test_short_symbol_span_not_flagged() -> None:
    # Span rất ngắn toàn ký hiệu Latin-1 hợp lệ (« » °) không đủ chữ → không gắn cờ legacy.
    assert classify_span("Literata", "« »", DetectConfig()) == TEXT_UNICODE
    assert classify_span("Literata", "°C", DetectConfig()) == TEXT_UNICODE
