"""Điểm 2 — tín hiệu legacy mạnh hơn, kiểm bằng **bảng TCVN3 chuẩn** (libiconv) + văn bản có dấu
tiếng Pháp/Anh/Tây Ban Nha (không được gắn legacy).

Bảng ``_TCVN3_2UNI`` là ``tcvn_2uni_2[128]`` lấy nguyên từ libiconv ``lib/tcvn.h`` (byte 0x80–0xFF
→ Unicode). Ta nghịch đảo để **mã hóa** chữ Việt Unicode thành byte TCVN3, rồi đọc byte đó như
Latin-1 — đúng kiểu "rác" mà một PDF font ABC xuất ra khi không có ToUnicode.
"""

from sepia_pipeline.detect import (
    LEGACY_OTHER,
    TEXT_UNICODE,
    DetectConfig,
    classify_span,
    has_real_vietnamese_unicode,
    legacy_char_ratio,
)

# tcvn_2uni_2[128]: byte (0x80 + index) → Unicode codepoint. Nguồn: libiconv lib/tcvn.h (v1.9).
_TCVN3_2UNI = [
    0x00C0, 0x1EA2, 0x00C3, 0x00C1, 0x1EA0, 0x1EB6, 0x1EAC, 0x00C8,
    0x1EBA, 0x1EBC, 0x00C9, 0x1EB8, 0x1EC6, 0x00CC, 0x1EC8, 0x0128,
    0x00CD, 0x1ECA, 0x00D2, 0x1ECE, 0x00D5, 0x00D3, 0x1ECC, 0x1ED8,
    0x1EDC, 0x1EDE, 0x1EE0, 0x1EDA, 0x1EE2, 0x00D9, 0x1EE6, 0x0168,
    0x00A0, 0x0102, 0x00C2, 0x00CA, 0x00D4, 0x01A0, 0x01AF, 0x0110,
    0x0103, 0x00E2, 0x00EA, 0x00F4, 0x01A1, 0x01B0, 0x0111, 0x1EB0,
    0x0300, 0x0309, 0x0303, 0x0301, 0x0323, 0x00E0, 0x1EA3, 0x00E3,
    0x00E1, 0x1EA1, 0x1EB2, 0x1EB1, 0x1EB3, 0x1EB5, 0x1EAF, 0x1EB4,
    0x1EAE, 0x1EA6, 0x1EA8, 0x1EAA, 0x1EA4, 0x1EC0, 0x1EB7, 0x1EA7,
    0x1EA9, 0x1EAB, 0x1EA5, 0x1EAD, 0x00E8, 0x1EC2, 0x1EBB, 0x1EBD,
    0x00E9, 0x1EB9, 0x1EC1, 0x1EC3, 0x1EC5, 0x1EBF, 0x1EC7, 0x00EC,
    0x1EC9, 0x1EC4, 0x1EBE, 0x1ED2, 0x0129, 0x00ED, 0x1ECB, 0x00F2,
    0x1ED4, 0x1ECF, 0x00F5, 0x00F3, 0x1ECD, 0x1ED3, 0x1ED5, 0x1ED7,
    0x1ED1, 0x1ED9, 0x1EDD, 0x1EDF, 0x1EE1, 0x1EDB, 0x1EE3, 0x00F9,
    0x1ED6, 0x1EE7, 0x0169, 0x00FA, 0x1EE5, 0x1EEB, 0x1EED, 0x1EEF,
    0x1EE9, 0x1EF1, 0x1EF3, 0x1EF7, 0x1EF9, 0x00FD, 0x1EF5, 0x1ED0,
]

# Nghịch đảo: ký tự Unicode → byte TCVN3 (bỏ dấu kết hợp 0x0300–0x036F và nbsp).
_UNI_2TCVN3: dict[str, int] = {}
for _i, _cp in enumerate(_TCVN3_2UNI):
    if 0x0300 <= _cp <= 0x036F or _cp == 0x00A0:
        continue
    _UNI_2TCVN3.setdefault(chr(_cp), 0x80 + _i)


def encode_tcvn3(text: str) -> str:
    """Mã hóa chữ Việt Unicode thành "rác" TCVN3 (byte TCVN3 đọc như Latin-1).

    ASCII giữ nguyên; ký tự Việt có dấu → byte TCVN3 tương ứng. Ký tự không có trong bảng → lỗi
    (chọn câu test chỉ dùng ký tự có trong bảng).
    """
    out = bytearray()
    for ch in text:
        if ord(ch) < 0x80:
            out.append(ord(ch))
        else:
            out.append(_UNI_2TCVN3[ch])
    return out.decode("latin-1")


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
