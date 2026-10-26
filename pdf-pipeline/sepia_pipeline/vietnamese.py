"""Bộ kiểm **âm tiết tiếng Việt** + chấm điểm khối chữ — dùng lọc dòng rác OCR (docs/03 §8).

KHÔNG phải từ điển: chỉ kiểm **cấu trúc âm tiết** (phụ âm đầu hợp lệ + vần hợp lệ + ≤ 1 dấu
thanh). Mục tiêu là **phân biệt chữ Việt thật với rác OCR** (vd ``?>?H$ 4 í im Àub1$ *íhA``), không
phải chấm đúng chính tả. Vì vậy chấm điểm ở **mức khối** (tỷ lệ token là âm tiết hợp lệ): một câu
có xen từ nước ngoài / chữ Hán vẫn điểm cao, không bị loại oan. Hoa/thường đều nhận; chuẩn hoá NFC
trước khi xét.

Thuần Python (không đụng PyMuPDF) để ``reflow`` nhập được mà vẫn giữ ranh giới "hàm thuần".
"""

from __future__ import annotations

import unicodedata

# Dải CJK whitelist — chữ Hán chèn trong sách Việt KHÔNG phải rác (song song với ``detect.is_cjk``;
# chép lại ở đây để module này không kéo theo PyMuPDF qua ``detect``).
_CJK_RANGES = ((0x4E00, 0x9FFF), (0x3400, 0x4DBF), (0xF900, 0xFAFF))

# Dấu thanh (combining) — một âm tiết hợp lệ có **tối đa một** dấu thanh (thanh ngang = không dấu).
# huyền 0300, sắc 0301, ngã 0303, hỏi 0309, nặng 0323. (Mũ 0302, trăng 0306, móc 031B là dấu
# **chất lượng nguyên âm** â/ă/ê/ô/ơ/ư — KHÔNG phải dấu thanh, giữ lại khi bỏ thanh.)
_TONE_MARKS = frozenset("̣̀́̃̉")

# Chữ cái bảng tiếng Việt (dạng đã bỏ dấu thanh, thường). KHÔNG có f j w z.
_VN_LETTERS = frozenset("abcdeghiklmnopqrstuvxy") | frozenset("ăâêôơưđ")

# Phụ âm đầu hợp lệ — thử DÀI trước NGẮN để khớp đúng ngh/ng/nh/ch… (và lùi về onset ngắn hơn khi
# onset dài làm vần rỗng, vd "gì" = g + i chứ không phải digraph "gi" rồi rỗng vần).
_ONSETS = (
    "ngh", "ng", "nh", "ch", "gh", "gi", "kh", "ph", "th", "tr", "qu",
    "b", "c", "d", "đ", "g", "h", "k", "l", "m", "n", "p", "r", "s", "t", "v", "x",
)

# Phụ âm cuối hợp lệ — thử DÀI trước NGẮN.
_FINALS = ("ng", "nh", "ch", "c", "m", "n", "p", "t")

# Vần cái (nguyên âm, đã bỏ dấu thanh, giữ â/ă/ê/ô/ơ/ư). Đủ các nguyên âm đơn/đôi/ba thông dụng —
# đây là heuristic để lọc rác, chấp nhận hơi "rộng" (nhận cả vài tổ hợp hiếm) hơn là loại oan chữ
# thật.
_NUCLEI = frozenset({
    # đơn
    "a", "ă", "â", "e", "ê", "i", "o", "ô", "ơ", "u", "ư", "y",
    # đôi
    "ai", "ao", "au", "ay", "âu", "ây",
    "eo", "êu",
    "ia", "iê", "iu", "yê",
    "oa", "oă", "oe", "oi", "oo", "ôi", "ơi",
    "ua", "uâ", "uê", "ui", "uô", "uơ", "uy", "ưa", "ươ", "ưi", "ưu",
    # ba
    "iêu", "yêu", "oai", "oao", "oay", "oeo",
    "uai", "uay", "uây", "uôi", "uya", "uyê", "uyu", "ươi", "ươu",
})


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _CJK_RANGES)


def _strip_tone(nfc_lower: str) -> tuple[str, int]:
    """Trả ``(âm tiết đã bỏ dấu thanh — giữ dấu chất lượng, NFC, số dấu thanh)``."""
    decomposed = unicodedata.normalize("NFD", nfc_lower)
    tones = sum(1 for ch in decomposed if ch in _TONE_MARKS)
    without = "".join(ch for ch in decomposed if ch not in _TONE_MARKS)
    return unicodedata.normalize("NFC", without), tones


def _is_valid_rime(rime: str) -> bool:
    """Vần = vần-cái + phụ âm cuối (tuỳ chọn)."""
    if not rime:
        return False
    if rime in _NUCLEI:
        return True
    for final in _FINALS:
        if rime.endswith(final):
            nucleus = rime[: -len(final)]
            if nucleus in _NUCLEI:
                return True
    return False


def _parse_onset_rime(base: str) -> bool:
    """True nếu ``base`` (đã bỏ dấu thanh) tách được thành phụ-âm-đầu-hợp-lệ + vần-hợp-lệ."""
    # Ứng viên: không phụ âm đầu (nguyên âm đứng đầu) + từng onset cắt ra (lùi dần độ dài).
    candidates = [base]
    for onset in _ONSETS:
        if base.startswith(onset) and len(base) > len(onset):
            candidates.append(base[len(onset):])
    return any(_is_valid_rime(rime) for rime in candidates)


def is_vietnamese_syllable(token: str) -> bool:
    """True nếu ``token`` là một âm tiết tiếng Việt hợp lệ về cấu trúc.

    - Token có **chữ Hán (CJK)** → coi là hợp lệ (chèn trong sách Việt, không phải rác).
    - Bỏ dấu thanh; > 1 dấu thanh → không hợp lệ.
    - Chỉ gồm chữ cái tiếng Việt (số / ký hiệu / f·j·w·z → không hợp lệ).
    - Tách phụ âm đầu + vần theo bảng âm tiết.
    """
    if not token:
        return False
    if any(_is_cjk(ch) for ch in token):
        return True
    nfc_lower = unicodedata.normalize("NFC", token).lower()
    base, tones = _strip_tone(nfc_lower)
    if tones > 1 or not base:
        return False
    if any(ch not in _VN_LETTERS for ch in base):
        return False
    return _parse_onset_rime(base)


def _is_number(core: str) -> bool:
    return all(ch.isdigit() for ch in core)


def _strip_edge_punct(token: str) -> str:
    """Bỏ dấu câu ở hai đầu token (giữ chữ/số/CJK bên trong). Vd ``(Đông,`` → ``Đông``."""

    def keep(ch: str) -> bool:
        return ch.isalnum() or _is_cjk(ch)

    start, end = 0, len(token)
    while start < end and not keep(token[start]):
        start += 1
    while end > start and not keep(token[end - 1]):
        end -= 1
    return token[start:end]


def vietnamese_score(text: str) -> float:
    """Tỷ lệ token là **âm tiết Việt hợp lệ** trong ``text``.

    Bỏ qua token chỉ gồm số và token chỉ gồm dấu câu (không tính vào mẫu số). Token có CJK coi là
    hợp lệ. Không có token chữ nào → trả ``1.0`` (không coi là rác, tránh bỏ nhầm tiêu đề toàn số).
    """
    scorable = 0
    valid = 0
    for raw in text.split():
        core = _strip_edge_punct(raw)
        if not core or _is_number(core):
            continue
        scorable += 1
        if is_vietnamese_syllable(core):
            valid += 1
    if scorable == 0:
        return 1.0
    return valid / scorable
