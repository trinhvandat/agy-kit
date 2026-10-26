"""Chuyển mã font cũ TCVN3/VNI → Unicode (ADR-005), chạy **sau khi trích, theo từng span**.

Luồng (docs/03 §2, §4): trích span (kèm tên font) → ``detect.classify_span`` gắn nhãn encoding →
span nào là ``legacy_tcvn3`` thì áp bảng chuyển ở đây rồi **NFC**. Không chạy trước bước trích
vì một trang có thể trộn nhiều font.

**Bảng TCVN3** ``TCVN3_2UNI`` lấy từ libiconv ``lib/tcvn.h`` (``tcvn_2uni_2[128]``): byte 0x80–0xFF
→ Unicode codepoint. Đây là **một nguồn duy nhất** — test import từ đây, không chép lại.

**VNI**: chưa có bảng (cần port từ VietUnicode) và **không có sách VNI trong mẫu** để xác thực
(SPIKE-3). Span nhãn ``legacy_vni``/``legacy_other`` tạm **giữ nguyên** + ghi cảnh báo, không đoán
bừa (đổi mã sai còn hại hơn để nguyên).
"""

from __future__ import annotations

import unicodedata

from .detect import (
    LEGACY_TCVN3,
    DetectConfig,
    classify_span,
)

# tcvn_2uni_2[128]: byte (0x80 + index) → Unicode codepoint. Nguồn: libiconv lib/tcvn.h (v1.9).
# Vài vị trí là **dấu kết hợp** (U+0300–U+0323) — sau khi map sẽ được NFC gộp vào nguyên âm đứng
# trước (vd "ơ" + U+0300 → "ờ").
TCVN3_2UNI: tuple[int, ...] = (
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
)


def decode_tcvn3(text: str) -> str:
    """Giải mã chuỗi "rác" TCVN3 (byte TCVN3 đọc nhầm thành Latin-1) → Unicode NFC.

    Mỗi ký tự: ASCII (<0x80) giữ nguyên; byte ≥0x80 map qua :data:`TCVN3_2UNI` (có thể ra dấu kết
    hợp). Cuối cùng **NFC** để gộp nguyên âm + dấu thành ký tự dựng sẵn.
    """
    out: list[str] = []
    for ch in text:
        cp = ord(ch)
        if cp < 0x80:
            out.append(ch)
        elif 0x80 <= cp <= 0xFF:
            out.append(chr(TCVN3_2UNI[cp - 0x80]))
        else:
            # Đã là Unicode (không phải rác Latin-1) → giữ nguyên.
            out.append(ch)
    return unicodedata.normalize("NFC", "".join(out))


# Bảng nghịch đảo để **mã hóa** Unicode → "rác" TCVN3 — chỉ dùng cho test / SPIKE-3 (tổng hợp dữ
# liệu minh họa khi không có sách TCVN3 thật). Bỏ qua dấu kết hợp và nbsp khi dựng nghịch đảo.
_UNI_2TCVN3: dict[str, int] = {}
for _i, _cp in enumerate(TCVN3_2UNI):
    if 0x0300 <= _cp <= 0x036F or _cp == 0x00A0:
        continue
    _UNI_2TCVN3.setdefault(chr(_cp), 0x80 + _i)


def encode_tcvn3(text: str) -> str:
    """Mã hóa chữ Việt Unicode (NFC) thành "rác" TCVN3 (byte TCVN3 đọc như Latin-1).

    Chỉ dùng cho test / tạo dữ liệu minh họa. Ký tự không có trong bảng (vd dấu kết hợp lạ) → lỗi
    ``KeyError`` để test biết mà chọn chuỗi hợp lệ.
    """
    text = unicodedata.normalize("NFC", text)
    out = bytearray()
    for ch in text:
        if ord(ch) < 0x80:
            out.append(ord(ch))
        else:
            out.append(_UNI_2TCVN3[ch])
    return out.decode("latin-1")


def convert_text(text: str, label: str) -> str:
    """Chuyển ``text`` theo nhãn encoding của span (xem :func:`detect.classify_span`).

    - ``legacy_tcvn3`` → :func:`decode_tcvn3`.
    - còn lại (unicode / vni / other) → giữ nguyên (chưa có bảng VNI; không đoán bừa).
    """
    if label == LEGACY_TCVN3:
        return decode_tcvn3(text)
    return text


def convert_span_text(
    font_name: str | None, text: str, config: DetectConfig | None = None
) -> tuple[str, str]:
    """Phân loại span theo (tên font, nội dung) rồi chuyển mã. Trả ``(text_đã_chuyển, nhãn)``."""
    config = config or DetectConfig()
    label = classify_span(font_name, text, config)
    return convert_text(text, label), label
