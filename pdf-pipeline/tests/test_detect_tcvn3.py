"""Điểm 2 — tín hiệu legacy mạnh hơn, kiểm bằng **bảng TCVN3 chuẩn** (libiconv) + văn bản có dấu
tiếng Pháp/Anh/Tây Ban Nha (không được gắn legacy).

Bảng TCVN3 và ``encode_tcvn3`` **một nguồn duy nhất** nằm trong ``sepia_pipeline.legacy_encoding``
(xem Bước 3, docs/03 §4) — test import từ đó, không chép lại. ``encode_tcvn3`` nghịch đảo bảng để
**mã hóa** chữ Việt Unicode thành byte TCVN3 rồi đọc như Latin-1 — đúng kiểu "rác" mà một PDF font
ABC xuất ra khi không có ToUnicode.
"""

from sepia_pipeline.detect import (
    LEGACY_OTHER,
    TEXT_UNICODE,
    DetectConfig,
    classify_span,
    has_real_vietnamese_unicode,
    legacy_char_ratio,
)
from sepia_pipeline.legacy_encoding import encode_tcvn3

# Vài đoạn văn tiếng Việt mã hóa TCVN3 (rác) — PHẢI bị gắn legacy.
_VN_PARAGRAPHS = [
    "Trong y học cổ truyền, huyệt vị là những điểm đặc biệt trên cơ thể con người",
    "Người bệnh cần được châm cứu đúng huyệt để khí huyết lưu thông điều hòa",
]

# Văn bản có dấu nhưng KHÔNG phải tiếng Việt — PHẢI KHÔNG bị gắn legacy.
_NON_VI_ACCENTED = [
    "Ça caractérise une drôle d'impression naïve et aiguë dans la forêt où il hésite souvent",
    "Le garçon reçut un cadeau spécial de sa marraine française pour un anniversaire joyeux",
    "The naive cafe served an elegant resume to every eager candidate early this bright morning",
    "El nino jugaba en el jardin mientras la senora cantaba una vieja cancion de cuna",
]


def test_encode_tcvn3_matches_known_garbage() -> None:
    # Kiểm encoder: "học" → "häc" (ọ = byte 0xE4 = 'ä' latin-1).
    assert encode_tcvn3("học") == "häc"


def test_tcvn3_paragraphs_flagged_legacy() -> None:
    cfg = DetectConfig()
    for vn in _VN_PARAGRAPHS:
        garbage = encode_tcvn3(vn)
        assert not has_real_vietnamese_unicode(garbage)
        assert legacy_char_ratio(garbage) > 0.15
        assert classify_span("CleanFont", garbage, cfg) == LEGACY_OTHER


def test_non_vietnamese_accented_not_flagged() -> None:
    cfg = DetectConfig()
    for text in _NON_VI_ACCENTED:
        assert classify_span("CleanFont", text, cfg) == TEXT_UNICODE


# Partial mis-decode: phần lớn ASCII + vài từ rác → ratio ~0.10 (trong [0.08, 0.15)).
_BORDERLINE = (
    "Trong cac tai lieu co ban nguoi ta thuong nhac den "
    + encode_tcvn3("huyệt vị, kinh mạch, điểm đặc biệt")
    + " tren co the nguoi"
)


def test_borderline_flipped_by_no_vi_signal() -> None:
    # Văn bản dài, có ký tự nghi, KHÔNG có chữ Việt Unicode thật → hạ ngưỡng (điểm 2) bắt được.
    assert 0.08 <= legacy_char_ratio(_BORDERLINE) < 0.15
    assert not has_real_vietnamese_unicode(_BORDERLINE)
    on = DetectConfig()
    off = DetectConfig(legacy_long_text_chars=10_000)  # vô hiệu hóa tín hiệu "không VN"
    assert classify_span("CleanFont", _BORDERLINE, on) == LEGACY_OTHER
    assert classify_span("CleanFont", _BORDERLINE, off) == TEXT_UNICODE


def test_no_vi_signal_does_not_flag_french() -> None:
    # Tiếng Pháp nhiều cedilla vẫn dưới ngưỡng hạ (0.08) → không bị gắn legacy dù hạ ngưỡng.
    fr = "Nous façonnons des maçonneries françaises avec une conscience et un soupçon de douceur"
    assert classify_span("CleanFont", fr, DetectConfig()) == TEXT_UNICODE
