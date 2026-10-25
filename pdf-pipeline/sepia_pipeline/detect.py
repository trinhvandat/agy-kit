"""Phát hiện loại PDF & font (Mốc 0, bước `detect`).

Phân loại **theo trang** và **theo span** (xem docs/03-pdf-pipeline.md §3):

- Trang: `text_unicode | legacy_tcvn3 | legacy_vni | legacy_other | scan | empty | mixed`.
- Cuốn: nhãn chiếm đa số + phân bố theo trang.

Thiết kế **để dễ bọc thành service**: phần lõi là **hàm thuần** (nhận chuỗi/dict/bbox, trả
kết quả có cấu trúc) — test được mà không cần PyMuPDF. Các adapter `detect_page`/`detect_pdf`
là lớp mỏng bọc PyMuPDF. **Không** dùng cấu hình toàn cục: mọi ngưỡng đi qua `DetectConfig`.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf as fitz

# --- Nhãn encoding mức span / nhãn trang ---------------------------------------

TEXT_UNICODE = "text_unicode"
LEGACY_TCVN3 = "legacy_tcvn3"
LEGACY_VNI = "legacy_vni"
LEGACY_OTHER = "legacy_other"
SCAN = "scan"
EMPTY = "empty"
MIXED = "mixed"

_LEGACY_LABELS = frozenset({LEGACY_TCVN3, LEGACY_VNI, LEGACY_OTHER})


# --- Cấu hình ngưỡng (không dùng cấu hình toàn cục) ----------------------------


@dataclass(frozen=True)
class DetectConfig:
    """Ngưỡng phân loại — truyền tường minh, có thể chỉnh.

    - ``scan_min_chars``: dưới mức này (ký tự không tính khoảng trắng) → trang "ít chữ".
    - ``scan_image_coverage``: ít chữ **và** ảnh phủ ≥ tỷ lệ này → ``scan`` (ngược lại ``empty``).
    - ``legacy_char_ratio_threshold``: tỷ lệ ký tự "nghi legacy" vượt mức này → gắn cờ legacy
      dù tên font sạch (bắt font bị đổi tên). **Heuristic để gắn cờ nghi ngờ, không tuyệt đối.**
    - ``mixed_min_fraction``: ≥ 2 loại mã, mỗi loại chiếm ≥ tỷ lệ này chữ của trang → ``mixed``.
    """

    scan_min_chars: int = 30
    scan_image_coverage: float = 0.70
    legacy_char_ratio_threshold: float = 0.15
    mixed_min_fraction: float = 0.15


# --- Heuristic thống kê ký tự --------------------------------------------------

# Dải CJK whitelist: chữ Hán chèn trong sách Việt KHÔNG tính là ký tự bất thường.
_CJK_RANGES = (
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0x3400, 0x4DBF),  # Extension A
    (0xF900, 0xFAFF),  # CJK Compatibility Ideographs
)


def is_cjk(ch: str) -> bool:
    """True nếu ``ch`` nằm trong dải CJK được whitelist."""
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _CJK_RANGES)


def _is_legacy_suspect(ch: str) -> bool:
    """Ký tự "nghi" là dấu tiếng Việt bị mã hóa TCVN3/VNI rút ra thành rác.

    Vùng Latin-1 ``0x80–0xBF`` (C1 + dấu câu/ký hiệu Latin-1) — KHÔNG phải chữ cái Việt
    Unicode hợp lệ nào nằm ở đây (các nguyên âm có dấu precomposed bắt đầu từ ``0xC0``).
    Một số ký tự vùng này (vd « » ° µ) đôi khi dùng hợp lệ → vì vậy dùng **tỷ lệ**, không tuyệt đối.
    """
    return 0x80 <= ord(ch) <= 0xBF


def legacy_char_ratio(text: str) -> float:
    """Tỷ lệ ký tự "nghi legacy" trên tổng ký tự chữ (loại CJK, khoảng trắng, chữ số).

    Mẫu số = số ký tự chữ-cái (không CJK) + số ký tự nghi. Tử số = số ký tự nghi.
    Văn bản Unicode sạch → ~0; văn bản TCVN3/VNI rút ra thành rác → cao.
    """
    suspect = 0
    letters = 0
    for ch in text:
        if is_cjk(ch):
            continue
        if _is_legacy_suspect(ch):
            suspect += 1
        elif ch.isalpha():
            letters += 1
    denom = suspect + letters
    if denom == 0:
        return 0.0
    return suspect / denom


def classify_span(font_name: str | None, text: str, config: DetectConfig) -> str:
    """Phân loại encoding của một span: ưu tiên tên font, rồi tới heuristic ký tự."""
    by_name = classify_font_name(font_name)
    if by_name is not None:
        return by_name
    if legacy_char_ratio(text) >= config.legacy_char_ratio_threshold:
        return LEGACY_OTHER
    return TEXT_UNICODE


# --- Độ phủ ảnh & nhãn trang ---------------------------------------------------


def image_coverage(
    bboxes: list[tuple[float, float, float, float]], page_area: float
) -> float:
    """Tỷ lệ che phủ của **ảnh lớn nhất** trên diện tích trang (0..1).

    Dùng ảnh lớn nhất (không cộng dồn) vì một trang scan điển hình là **một** ảnh phủ kín;
    cộng dồn các ảnh chồng nhau sẽ phóng đại. An toàn khi ``page_area`` = 0.
    """
    if page_area <= 0 or not bboxes:
        return 0.0
    best = 0.0
    for x0, y0, x1, y1 in bboxes:
        area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
        best = max(best, area)
    return min(1.0, best / page_area)


def classify_page(
    spans: list[tuple[str | None, str]],
    char_count: int,
    image_coverage: float,
    config: DetectConfig,
) -> str:
    """Gộp các span thành một nhãn trang.

    Trang ít chữ (``char_count < scan_min_chars``) được quyết trước: có ảnh lớn → ``scan``,
    không → ``empty`` (ưu tiên này bắt cả trang scan có vài chú thích nhỏ). Ngược lại gộp
    encoding từng span (theo số ký tự không-trắng): nếu ≥ 2 loại mã cùng đáng kể → ``mixed``,
    nếu không → loại chiếm ưu thế.
    """
    if char_count < config.scan_min_chars:
        return SCAN if image_coverage >= config.scan_image_coverage else EMPTY

    counts: dict[str, int] = {}
    for font_name, text in spans:
        weight = sum(1 for ch in text if not ch.isspace())
        if weight == 0:
            continue
        label = classify_span(font_name, text, config)
        counts[label] = counts.get(label, 0) + weight

    if not counts:
        # Có char_count nhưng span rỗng (hiếm) — coi như Unicode mặc định.
        return TEXT_UNICODE

    total = sum(counts.values())
    significant = {
        label for label, n in counts.items() if n / total >= config.mixed_min_fraction
    }
    if len(significant) >= 2:
        return MIXED
    # Một loại chiếm ưu thế → trả loại có nhiều ký tự nhất.
    return max(counts, key=lambda label: counts[label])


# --- Kết quả có cấu trúc -------------------------------------------------------


@dataclass(frozen=True)
class PageResult:
    """Kết quả một trang."""

    page_number: int  # 1-based
    label: str
    char_count: int
    image_coverage: float
    legacy_ratio: float
    legacy_fonts: tuple[str, ...] = ()


@dataclass(frozen=True)
class BookResult:
    """Kết quả một cuốn (hoặc lỗi)."""

    path: str
    label: str | None
    n_pages: int
    page_distribution: dict[str, int] = field(default_factory=dict)
    legacy_fonts: tuple[str, ...] = ()
    scan_pages: int = 0
    empty_pages: int = 0
    pages: tuple[PageResult, ...] = ()
    error: str | None = None


# --- Adapter PyMuPDF (lớp mỏng) ------------------------------------------------


def _non_space_len(text: str) -> int:
    return sum(1 for ch in text if not ch.isspace())


def _page_spans(page: fitz.Page) -> list[tuple[str | None, str]]:
    """Lấy (tên font, text) của từng span qua ``get_text("dict")``."""
    data = page.get_text("dict")
    spans: list[tuple[str | None, str]] = []
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                spans.append((span.get("font"), span.get("text", "")))
    return spans


def _page_image_coverage(page: fitz.Page) -> float:
    page_area = page.rect.width * page.rect.height
    try:
        infos = page.get_image_info()
    except Exception:
        return 0.0
    bboxes = [tuple(info["bbox"]) for info in infos if "bbox" in info]
    return image_coverage(bboxes, page_area)


def detect_page(page: fitz.Page, config: DetectConfig) -> PageResult:
    """Phân loại một trang PyMuPDF."""
    text = page.get_text()
    char_count = _non_space_len(text)
    spans = _page_spans(page)
    coverage = _page_image_coverage(page)
    label = classify_page(spans, char_count, coverage, config)
    legacy_fonts = tuple(
        sorted({fn for fn, _ in spans if fn and classify_font_name(fn) is not None})
    )
    return PageResult(
        page_number=page.number + 1,
        label=label,
        char_count=char_count,
        image_coverage=coverage,
        legacy_ratio=legacy_char_ratio(text),
        legacy_fonts=legacy_fonts,
    )


def _aggregate(path: str, pages: list[PageResult]) -> BookResult:
    distribution = dict(Counter(p.label for p in pages))
    # Nhãn cuốn = loại chiếm đa số; hòa → ưu tiên nhãn có số trang cao, rồi theo tên (ổn định).
    book_label = (
        max(distribution.items(), key=lambda kv: (kv[1], kv[0]))[0] if distribution else None
    )
    legacy_fonts = tuple(sorted({f for p in pages for f in p.legacy_fonts}))
    return BookResult(
        path=path,
        label=book_label,
        n_pages=len(pages),
        page_distribution=distribution,
        legacy_fonts=legacy_fonts,
        scan_pages=distribution.get(SCAN, 0),
        empty_pages=distribution.get(EMPTY, 0),
        pages=tuple(pages),
    )


def detect_pdf(path: str | Path, config: DetectConfig | None = None) -> BookResult:
    """Phân loại một file PDF.

    PDF lỗi / có mật khẩu → trả ``BookResult`` có ``error``, không crash.
    """
    config = config or DetectConfig()
    path_str = str(path)
    if not Path(path).exists():
        return BookResult(path=path_str, label=None, n_pages=0, error="file không tồn tại")
    doc = None
    try:
        doc = fitz.open(path_str)
        if doc.needs_pass:
            return BookResult(
                path=path_str, label=None, n_pages=0, error="PDF có mật khẩu (password-protected)"
            )
        pages = [detect_page(page, config) for page in doc]
        return _aggregate(path_str, pages)
    except Exception as exc:  # PDF hỏng / không mở được
        err = f"{type(exc).__name__}: {exc}"
        return BookResult(path=path_str, label=None, n_pages=0, error=err)
    finally:
        if doc is not None:
            doc.close()

# Tiền tố subset của PDF: đúng 6 chữ IN HOA + "+", vd "ABCDEF+".
_SUBSET = r"(?:[A-Z]{6}\+)?"

# TCVN3/ABC: tên bắt đầu bằng ".Vn" (dấu chấm có thể vắng ở vài bản), vd .VnTime, .VnArialH.
_TCVN3_RE = re.compile(rf"^{_SUBSET}\.?Vn[A-Za-z]*$")
# VNI: bắt đầu bằng "VNI-", vd VNI-Times, VNI-Helve.
_VNI_RE = re.compile(rf"^{_SUBSET}VNI-[A-Za-z]*$")


def classify_font_name(font_name: str | None) -> str | None:
    """Phân loại font cũ theo **tên span**, có xử lý tiền tố subset ``ABCDEF+``.

    Trả ``legacy_tcvn3`` / ``legacy_vni`` nếu khớp mẫu đã biết; ``None`` nếu tên sạch
    (vd ``TimesNewRomanPSMT``, ``ArialMT``). Dùng ``fullmatch`` để tránh dương tính giả
    (font sạch có chuỗi con giống mẫu sẽ không bị khớp). VPS/VISCII chưa có mẫu tên tin
    cậy nên không nhận ở đây — dựa vào heuristic ký tự (``legacy_char_ratio``).
    """
    if not font_name:
        return None
    if _TCVN3_RE.match(font_name):
        return LEGACY_TCVN3
    if _VNI_RE.match(font_name):
        return LEGACY_VNI
    return None
