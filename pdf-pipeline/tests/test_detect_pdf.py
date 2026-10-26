"""Cycle 4 — adapter PyMuPDF: detect_page / detect_pdf trên PDF sinh bằng code."""

from pathlib import Path

from sepia_pipeline.detect import (
    EMPTY,
    LEGACY_OTHER,
    SCAN,
    SCAN_OCR,
    TEXT_UNICODE,
    BookResult,
    DetectConfig,
    detect_page,
    detect_pdf,
)


class _Rect:
    width = 100.0
    height = 100.0


class _FakePage:
    """Trang giả: get_text("dict") trả span; get_text() KHÔNG tham số → lỗi (điểm 5).

    ``images`` = danh sách bbox; ``texttrace_calls`` đếm số lần get_texttrace được gọi.
    """

    number = 0
    rect = _Rect()

    def __init__(self, text: str, images: list | None = None) -> None:
        self._text = text
        self._images = images or []
        self.texttrace_calls = 0

    def get_text(self, kind: str | None = None):
        if kind != "dict":
            raise AssertionError("detect_page không được gọi get_text() thường (điểm 5)")
        return {"blocks": [{"lines": [{"spans": [{"font": "Literata", "text": self._text}]}]}]}

    def get_image_info(self):
        return [{"bbox": b} for b in self._images]

    def get_texttrace(self):
        self.texttrace_calls += 1
        return []


def test_detect_page_reads_text_from_dict_spans_only() -> None:
    text = "Tôi học huyệt vị Đông y mỗi ngày thật chăm chỉ và đều đặn"
    res = detect_page(_FakePage(text), DetectConfig())
    assert res.label == TEXT_UNICODE
    # char_count = số ký tự không-trắng lấy từ span của dict
    assert res.char_count == sum(1 for ch in text if not ch.isspace())


def test_texttrace_skipped_when_no_full_image() -> None:
    # Trang không có ảnh phủ kín → KHÔNG gọi get_texttrace, hidden_text_ratio = 0.0 (điểm 2).
    page = _FakePage("Tôi học huyệt vị Đông y mỗi ngày thật chăm chỉ và đều đặn")
    res = detect_page(page, DetectConfig())
    assert page.texttrace_calls == 0
    assert res.hidden_text_ratio == 0.0


def test_texttrace_called_when_full_image() -> None:
    # Ảnh phủ kín trang → get_texttrace được gọi để đo tỷ lệ chữ ẩn.
    page = _FakePage(
        "Tôi học huyệt vị Đông y mỗi ngày thật chăm chỉ và đều đặn",
        images=[(0, 0, 100, 100)],
    )
    detect_page(page, DetectConfig())
    assert page.texttrace_calls == 1


def test_page_result_lower_bound_false_for_normal_page() -> None:
    page = _FakePage("Tôi học huyệt vị Đông y mỗi ngày thật chăm chỉ và đều đặn")
    res = detect_page(page, DetectConfig())
    assert res.coverage_is_lower_bound is False


def test_page_result_lower_bound_true_when_early_stopped() -> None:
    # Nhiều ảnh lát kín (> ngưỡng lưới) → độ phủ dừng sớm → cờ lower_bound True.
    imgs = [(i % 20 * 5, i // 20 * 5, i % 20 * 5 + 5, i // 20 * 5 + 5) for i in range(400)]
    page = _FakePage("x" * 100, images=imgs)
    res = detect_page(page, DetectConfig())
    assert res.coverage_is_lower_bound is True


def test_unicode_book(unicode_vi_pdf: Path) -> None:
    res = detect_pdf(unicode_vi_pdf)
    assert isinstance(res, BookResult)
    assert res.error is None
    assert res.label == TEXT_UNICODE
    assert res.n_pages == 1
    assert res.page_distribution.get(TEXT_UNICODE) == 1


def test_unicode_book_keeps_han_without_flagging_garbage(unicode_vi_pdf: Path) -> None:
    # Chữ Hán không bị đếm là rác → không gắn cờ legacy.
    res = detect_pdf(unicode_vi_pdf)
    assert res.pages[0].legacy_ratio < 0.05


def test_tcvn3_garbage_book_flagged_legacy(tcvn3_garbage_pdf: Path) -> None:
    res = detect_pdf(tcvn3_garbage_pdf)
    # Font tên sạch (helv) nhưng text là rác → heuristic gắn legacy_other.
    assert res.label == LEGACY_OTHER
    assert res.pages[0].legacy_ratio > 0.15


def test_scan_book(scan_pdf: Path) -> None:
    res = detect_pdf(scan_pdf)
    assert res.label == SCAN
    assert res.scan_pages == 1


def test_scan_ocr_book(scan_ocr_pdf: Path) -> None:
    res = detect_pdf(scan_ocr_pdf)
    assert res.label == SCAN_OCR
    # Lớp chữ ẩn (render mode 3) được ghi lại; cờ ảnh phủ kín bật.
    assert res.pages[0].hidden_text_ratio > 0.9
    assert res.pages[0].has_full_page_image is True


def test_full_image_visible_text_is_text_unicode(full_image_visible_text_pdf: Path) -> None:
    res = detect_pdf(full_image_visible_text_pdf)
    assert res.label == TEXT_UNICODE
    assert res.pages[0].has_full_page_image is True  # vẫn ghi nhận có ảnh phủ kín
    assert res.pages[0].hidden_text_ratio < 0.5  # chữ hiển thị, không phải lớp OCR ẩn


def test_empty_book(empty_pdf: Path) -> None:
    res = detect_pdf(empty_pdf)
    assert res.label == EMPTY
    assert res.empty_pages == 1


def test_multi_page_distribution(multi_page_pdf: Path) -> None:
    res = detect_pdf(multi_page_pdf)
    assert res.n_pages == 3
    assert res.page_distribution.get(TEXT_UNICODE) == 2
    assert res.page_distribution.get(EMPTY) == 1
    assert res.label == TEXT_UNICODE  # đa số


def test_corrupt_pdf_returns_error_not_crash(corrupt_pdf: Path) -> None:
    res = detect_pdf(corrupt_pdf)
    assert res.error is not None
    assert res.label is None
    assert res.n_pages == 0


def test_encrypted_pdf_returns_error_not_crash(encrypted_pdf: Path) -> None:
    res = detect_pdf(encrypted_pdf)
    assert res.error is not None
    assert "password" in res.error.lower() or "mật khẩu" in res.error.lower()


def test_missing_file_returns_error(tmp_path: Path) -> None:
    res = detect_pdf(tmp_path / "khong-ton-tai.pdf")
    assert res.error is not None


def test_scan_ocr_visible_book_labeled_scan_ocr(scan_ocr_visible_book_pdf: Path) -> None:
    # Sách scan ABBYY: mọi trang ảnh phủ kín + chữ OCR hiển thị → nhãn cuốn scan_ocr (mức CUỐN).
    res = detect_pdf(scan_ocr_visible_book_pdf)
    assert res.label == SCAN_OCR
    assert res.producer == "ABBYY FineReader 11"
    assert res.creator == "Foxit"
    # Trang lẻ vẫn được gán theo nội dung (có chữ hiển thị) — không phải trang nào cũng scan_ocr.
    assert res.page_distribution.get(TEXT_UNICODE, 0) >= 1


def test_single_image_page_does_not_flip_book(multi_page_pdf: Path) -> None:
    # Sách chữ thường (không ảnh phủ kín) → KHÔNG bị gán scan_ocr.
    res = detect_pdf(multi_page_pdf)
    assert res.label == TEXT_UNICODE


def test_single_page_full_image_not_scan_ocr_book(full_image_visible_text_pdf: Path) -> None:
    # 1 trang ảnh nền + chữ hiển thị: quá ít trang (< min_pages) → KHÔNG kết luận cuốn scan_ocr.
    res = detect_pdf(full_image_visible_text_pdf)
    assert res.label != SCAN_OCR
    assert res.label == TEXT_UNICODE
