"""Test bộ kiểm âm tiết tiếng Việt + chấm điểm khối chữ (dùng lọc dòng rác OCR)."""

import unicodedata

import pytest

from sepia_pipeline.vietnamese import (
    is_vietnamese_syllable,
    looks_vietnamese,
    vietnamese_score,
)

# --- is_vietnamese_syllable: âm tiết thật (phải HỢP LỆ) -----------------------


def test_common_syllables_valid() -> None:
    for s in [
        "dưỡng",
        "sinh",
        "mùa",
        "thu",
        "thể",
        "chất",
        "khí",
        "hư",
        "kinh",
        "mạch",
        "là",
        "gì",  # "g" + "i" (không phải digraph "gi" rồi rỗng vần)
        "nghe",
        "nghĩa",
        "quyết",
        "huyệt",
        "người",
        "ương",
        "uyên",
        "yêu",
        "khỏe",
        "nguyền",
    ]:
        assert is_vietnamese_syllable(s), f"{s!r} phải là âm tiết hợp lệ"


def test_case_insensitive() -> None:
    assert is_vietnamese_syllable("DƯỠNG")
    assert is_vietnamese_syllable("Sinh")
    assert is_vietnamese_syllable("KHÍ")


def test_accepts_nfd_input_normalizes_to_nfc() -> None:
    nfd = unicodedata.normalize("NFD", "dưỡng")
    assert nfd != "dưỡng"  # đúng là chuỗi NFD khác NFC
    assert is_vietnamese_syllable(nfd)


def test_cjk_token_is_valid() -> None:
    assert is_vietnamese_syllable("穴")  # chữ Hán chèn trong sách Việt
    assert is_vietnamese_syllable("經絡")


# --- is_vietnamese_syllable: rác (phải KHÔNG hợp lệ) --------------------------


def test_ocr_garbage_tokens_invalid() -> None:
    for s in [
        "H$",  # phụ âm + ký hiệu
        "xrq",  # cụm phụ âm không có nguyên âm
        "àub1",  # có chữ số bên trong
        "íhA",  # cụm không thành âm tiết
        "zjwf",  # chữ cái ngoài bảng tiếng Việt
        "bzz",
    ]:
        assert not is_vietnamese_syllable(s), f"{s!r} phải bị coi là KHÔNG hợp lệ"


def test_two_tone_marks_invalid() -> None:
    # Hai dấu thanh trên một âm tiết → không hợp lệ (âm tiết chỉ có một thanh).
    assert not is_vietnamese_syllable("áà")


def test_foreign_consonant_cluster_invalid() -> None:
    # "gram" / "spa": phụ âm đầu "gr"/"sp" không có trong tiếng Việt → từng token không hợp lệ.
    assert not is_vietnamese_syllable("gram")
    assert not is_vietnamese_syllable("spa")


# --- vietnamese_score: chấm điểm cả khối -------------------------------------


def test_score_real_heading_high() -> None:
    assert vietnamese_score("DƯỠNG SINH MÙA THU") == 1.0
    assert vietnamese_score("THỂ CHẤT KHÍ HƯ") == 1.0
    assert vietnamese_score("KINH MẠCH LÀ GÌ?") == 1.0  # dấu "?" đứng cuối bị bỏ qua


def test_score_garbage_heading_low() -> None:
    # Heading rác OCR của chữ trang trí.
    assert vietnamese_score("?>?H$ 4 í im Àub1$ *íhA") < 0.5


def test_score_ignores_numbers_and_standalone_punctuation() -> None:
    # "123" và "—" bị bỏ qua; chỉ tính token chữ.
    assert vietnamese_score("Trang 123 — Dưỡng sinh") == 1.0


def test_score_sentence_with_foreign_and_cjk_not_penalized() -> None:
    # Câu tiếng Việt có xen từ nước ngoài / chữ Hán → vẫn điểm cao (không bị loại oan).
    assert vietnamese_score("Đi spa và tập gram mỗi ngày thật tốt") >= 0.5
    assert vietnamese_score("Huyệt 穴 nằm trên kinh mạch經絡 của cơ thể") >= 0.5


def test_score_no_word_tokens_is_one() -> None:
    # Không có token chữ nào (chỉ số/dấu) → không coi là rác.
    assert vietnamese_score("123 456 — .") == 1.0
    assert vietnamese_score("") == 1.0


# --- vietnamese_score: token TRUNG TÍNH (không kéo điểm) ----------------------


@pytest.mark.parametrize(
    "text",
    [
        "Liều: 10–15 g",  # số + đơn vị
        "Vitamin B12",  # từ ngoại + mã
        "Bảng 3.2",  # số thập phân
        "Hợp Cốc (LI4)",  # tên huyệt + mã huyệt
        "DNA",  # viết tắt in hoa
        "TCM",
        "II.",  # số La Mã
        "Chương XII",
        "Email: info@huyhoangbook.vn",  # colophon email
        "www.huyhoangbook.com.vn",  # colophon website
        "Ma Hoàng (Ephedra sinica)",  # tên vị thuốc + tên khoa học
    ],
)
def test_score_neutral_tokens_not_penalized(text: str) -> None:
    # Mã/số, email/URL, từ viết tắt, số La Mã, từ ngoại → TRUNG TÍNH → khối vẫn ≥ 0.5 (được GIỮ).
    assert vietnamese_score(text) >= 0.5, f"{text!r} không được bị bỏ oan"


@pytest.mark.parametrize(
    "text",
    [
        "?>?H$ 4 í im Àub1$ *íhA",  # rác OCR chữ trang trí
        "= = ^ s -",
        "<*x>o-c*x>o<xx><>o<><xx<x>c^>c<xxx^^",
        "<D",  # một chữ cái đơn kèm ký hiệu
        "Q",  # một chữ cái đơn
    ],
)
def test_score_garbage_still_dropped(text: str) -> None:
    # Chữ cái đơn VẪN tính điểm + token có dấu-mojibake không trung tính → rác vẫn < 0.5 (bị BỎ).
    assert vietnamese_score(text) < 0.5, f"{text!r} phải bị coi là rác"


# --- looks_vietnamese: cổng bật/tắt lọc rác ----------------------------------


def test_looks_vietnamese_true_for_vietnamese() -> None:
    assert looks_vietnamese("Mùa thu khí trời hanh khô, cần dưỡng phế và giữ ẩm cơ thể con người.")


def test_looks_vietnamese_false_for_french_and_english() -> None:
    # Tiếng Pháp (é à â ô Latin-1) / tiếng Anh → KHÔNG có chữ Việt Unicode "thật" → False.
    assert not looks_vietnamese("La médecine générale est à la française, très développée.")
    assert not looks_vietnamese("A general introduction to the theory of medicine and health.")


def test_looks_vietnamese_false_for_too_few_real_chars() -> None:
    # Vài ký tự lạc lõng (OCR nhầm) trong văn bản không phải tiếng Việt → chưa đủ ngưỡng → False.
    assert not looks_vietnamese("Mostly english text with one stray ạ character here.")
