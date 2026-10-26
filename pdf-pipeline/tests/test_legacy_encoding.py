"""Test chuyển mã TCVN3 → Unicode (Bước 3 / ADR-005).

Không có sách TCVN3 thật trong ``samples/`` nên kiểm bằng **round-trip** (Unicode → TCVN3 "rác" →
giải mã lại) trên các đoạn Đông y, cộng vài ca cố định. VNI chưa có bảng → chỉ kiểm là "giữ nguyên".
"""

from sepia_pipeline.detect import LEGACY_TCVN3, LEGACY_VNI, TEXT_UNICODE, DetectConfig
from sepia_pipeline.legacy_encoding import (
    convert_span_text,
    convert_text,
    decode_tcvn3,
    encode_tcvn3,
)

# Đoạn Đông y dùng nhiều dấu/nguyên âm đặc trưng tiếng Việt.
_PARAS = [
    "Trong y học cổ truyền, huyệt vị là những điểm đặc biệt trên cơ thể con người.",
    "Người bệnh cần được châm cứu đúng huyệt để khí huyết lưu thông điều hòa.",
    "Thận chủ cốt sinh tủy, can chủ cân, tỳ chủ cơ nhục, phế chủ bì mao.",
    "Bài thuốc gồm: đương quy, xuyên khung, bạch thược, thục địa, bổ huyết điều kinh.",
]


def test_decode_known_case() -> None:
    # "học" mã TCVN3 là "häc" (ọ = byte 0xE4 đọc latin-1 = 'ä').
    assert encode_tcvn3("học") == "häc"
    assert decode_tcvn3("häc") == "học"


def test_roundtrip_paragraphs() -> None:
    for vn in _PARAS:
        garbage = encode_tcvn3(vn)
        assert garbage != vn  # thực sự thành "rác"
        assert decode_tcvn3(garbage) == vn  # giải mã lại khớp 100%


def test_decode_is_nfc() -> None:
    import unicodedata

    for vn in _PARAS:
        out = decode_tcvn3(encode_tcvn3(vn))
        assert out == unicodedata.normalize("NFC", out)


def test_ascii_untouched() -> None:
    assert decode_tcvn3("Chapter 1: 123 ABC xyz") == "Chapter 1: 123 ABC xyz"


def test_convert_text_by_label() -> None:
    garbage = encode_tcvn3("châm cứu")
    assert convert_text(garbage, LEGACY_TCVN3) == "châm cứu"
    # Nhãn khác → giữ nguyên (chưa có bảng VNI; không đoán bừa).
    assert convert_text(garbage, LEGACY_VNI) == garbage
    assert convert_text("hello", TEXT_UNICODE) == "hello"


def test_convert_span_uses_font_name() -> None:
    cfg = DetectConfig()
    garbage = encode_tcvn3("Thận chủ cốt sinh tủy")
    # Font .VnTime → nhận TCVN3 theo tên → giải mã.
    text, label = convert_span_text(".VnTime", garbage, cfg)
    assert label == LEGACY_TCVN3
    assert text == "Thận chủ cốt sinh tủy"
    # Font sạch + chữ Unicode thật → giữ nguyên.
    text2, label2 = convert_span_text("ArialMT", "Thận chủ cốt sinh tủy", cfg)
    assert label2 == TEXT_UNICODE
    assert text2 == "Thận chủ cốt sinh tủy"
