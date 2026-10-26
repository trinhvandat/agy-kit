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
    "ngh",
    "ng",
    "nh",
    "ch",
    "gh",
    "gi",
    "kh",
    "ph",
    "th",
    "tr",
    "qu",
    "b",
    "c",
    "d",
    "đ",
    "g",
    "h",
    "k",
    "l",
    "m",
    "n",
    "p",
    "r",
    "s",
    "t",
    "v",
    "x",
)

# Phụ âm cuối hợp lệ — thử DÀI trước NGẮN.
_FINALS = ("ng", "nh", "ch", "c", "m", "n", "p", "t")

# Vần cái (nguyên âm, đã bỏ dấu thanh, giữ â/ă/ê/ô/ơ/ư). Đủ các nguyên âm đơn/đôi/ba thông dụng —
# đây là heuristic để lọc rác, chấp nhận hơi "rộng" (nhận cả vài tổ hợp hiếm) hơn là loại oan chữ
# thật.
_NUCLEI = frozenset(
    {
        # đơn
        "a",
        "ă",
        "â",
        "e",
        "ê",
        "i",
        "o",
        "ô",
        "ơ",
        "u",
        "ư",
        "y",
        # đôi
        "ai",
        "ao",
        "au",
        "ay",
        "âu",
        "ây",
        "eo",
        "êu",
        "ia",
        "iê",
        "iu",
        "yê",
        "oa",
        "oă",
        "oe",
        "oi",
        "oo",
        "ôi",
        "ơi",
        "ua",
        "uâ",
        "uê",
        "ui",
        "uô",
        "uơ",
        "uy",
        "ưa",
        "ươ",
        "ưi",
        "ưu",
        # ba
        "iêu",
        "yêu",
        "oai",
        "oao",
        "oay",
        "oeo",
        "uai",
        "uay",
        "uây",
        "uôi",
        "uya",
        "uyê",
        "uyu",
        "ươi",
        "ươu",
    }
)


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
            candidates.append(base[len(onset) :])
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


# Chữ Việt Unicode "thật" ngoài Latin-1 (ă/â.. precomposed nằm trong Latin-1 nên KHÔNG tính) — dùng
# nhận biết "sách tiếng Việt" (:func:`looks_vietnamese`). Song song ``detect._VI_UNICODE_LETTERS``;
# chép lại để module này thuần (không kéo PyMuPDF qua ``detect``).
_VI_UNICODE_LETTERS = frozenset("ăĂđĐơƠưƯ")

# Dấu nối cho token "mã/số" (3.2, 10–15, Covid-19): gồm cả en/em dash (ngoài ASCII).
_CODE_SEPARATORS = frozenset("-–—./+:,")


def _is_ascii_letter(ch: str) -> bool:
    return ("a" <= ch <= "z") or ("A" <= ch <= "Z")


def _is_code_or_number(core: str) -> bool:
    """Token **mã/số**: có ≥1 chữ số và chỉ gồm chữ-số ASCII + vài dấu nối (3.2, 10–15, B12, LI4,
    Covid-19, CO2).

    Chữ cái **có dấu** (À, ế…) loại token khỏi nhóm này → rác mojibake như ``Àub1`` KHÔNG trung tính
    mà vẫn bị chấm là không hợp lệ.
    """
    if not any(ch.isdigit() for ch in core):
        return False
    return all((ch.isascii() and ch.isalnum()) or ch in _CODE_SEPARATORS for ch in core)


def _is_url_or_email(core: str) -> bool:
    """Token email/URL: có ``@`` hoặc chứa ``www.``/``http`` (colophon nhà sách, không phải rác)."""
    low = core.lower()
    return "@" in core or "www." in low or "http" in low


def _is_foreign_word(core: str) -> bool:
    """Từ "ngoại" thuần chữ cái ASCII, dài ≥ 2: từ nước ngoài (Vitamin, Email, Ephedra), viết tắt IN
    HOA (DNA, TCM), số La Mã (II, XII).

    **Trung tính** — không tính vào mẫu số (không thưởng, không phạt). Chữ cái **đơn** (len 1) KHÔNG
    thuộc nhóm này nên rác như "V"/"J"/"Q"/"<D" vẫn bị chấm không hợp lệ và bị bỏ.
    """
    return len(core) >= 2 and all(_is_ascii_letter(ch) for ch in core)


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

    **Token TRUNG TÍNH** (không tính vào mẫu số, không thưởng/không phạt): token chỉ gồm dấu câu;
    mã/số (:func:`_is_code_or_number` — 3.2, 10–15, B12, LI4, Covid-19, CO2); email/URL
    (:func:`_is_url_or_email`); từ ngoại/viết tắt/La Mã (:func:`_is_foreign_word` — Vitamin, Email,
    DNA, TCM, II, XII). Nhờ vậy nhãn/số liệu/colophon không kéo điểm xuống làm **bỏ oan** nội dung
    thật. Token có CJK coi là **hợp lệ**. Chữ cái **đơn** VẪN tính điểm nên rác một ký tự ("V",
    "<D") vẫn bị bỏ. Không có token chấm điểm nào → trả ``1.0`` (không coi là rác).
    """
    scorable = 0
    valid = 0
    for raw in text.split():
        core = _strip_edge_punct(raw)
        if not core:
            continue
        if _is_code_or_number(core) or _is_url_or_email(core) or _is_foreign_word(core):
            continue  # trung tính
        scorable += 1
        if is_vietnamese_syllable(core):
            valid += 1
    if scorable == 0:
        return 1.0
    return valid / scorable


def looks_vietnamese(text: str, *, min_real_chars: int = 8) -> bool:
    """True nếu ``text`` có đủ ký tự tiếng Việt Unicode "thật" để coi là **sách tiếng Việt**.

    "Thật" = khối ``U+1EA0–1EF9`` (ạ ả ấ ầ … ỹ) hoặc ă/â-ngoài-Latin-1 ă/đ/ơ/ư (và hoa). Tiếng
    Pháp/Anh dùng é à â ô (Latin-1) **không** tính → không dương tính giả. Cần ≥ ``min_real_chars``
    để bỏ qua vài ký tự lạc lõng (OCR nhầm) trong sách thật sự không phải tiếng Việt.

    Dùng làm **cổng** cho lọc rác âm tiết Việt: chỉ lọc khi sách là tiếng Việt (xem :mod:`convert`).
    """
    count = 0
    for ch in text:
        if 0x1EA0 <= ord(ch) <= 0x1EF9 or ch in _VI_UNICODE_LETTERS:
            count += 1
            if count >= min_real_chars:
                return True
    return False
