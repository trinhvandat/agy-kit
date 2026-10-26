"""Phát hiện loại PDF & font (Mốc 0, bước `detect`).

Phân loại **theo trang** và **theo span** (xem docs/03-pdf-pipeline.md §3):

- Trang: text_unicode | legacy_tcvn3 | legacy_vni | legacy_other | scan | scan_ocr | empty | mixed.
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
SCAN_OCR = "scan_ocr"
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
    - ``legacy_min_chars``: cần tối thiểu bấy nhiêu ký tự chữ/nghi mới tin heuristic (tránh dương
      tính giả ở span rất ngắn toàn ký hiệu, vd « » °).
    - ``legacy_long_text_chars`` + ``legacy_no_vi_ratio_threshold``: với văn bản **dài** (≥
      ``legacy_long_text_chars`` chữ cái) có ký tự nghi nhưng **không** có chữ Việt Unicode thật
      (mis-decode không bao giờ sinh ạ/ế/đ/ơ…), hạ ngưỡng xuống ``legacy_no_vi_ratio_threshold``
      để bắt mis-decode nhẹ. Tiếng Pháp/Anh ratio vốn rất thấp (<0.06) nên vẫn an toàn.
    - ``mixed_min_fraction``: ≥ 2 loại mã, mỗi loại chiếm ≥ tỷ lệ này chữ của trang → ``mixed``.
    - ``image_grid_threshold``: nhiều hơn bấy nhiêu ảnh thì tính độ phủ bằng **lưới thô** (nhanh)
      thay vì union chính xác (O(n²)).
    - ``image_grid_cells``: số ô mỗi chiều của lưới thô (vd 200 → lưới 200×200).
    """

    scan_min_chars: int = 30
    scan_image_coverage: float = 0.70
    legacy_char_ratio_threshold: float = 0.15
    legacy_min_chars: int = 6
    legacy_long_text_chars: int = 40
    legacy_no_vi_ratio_threshold: float = 0.08
    mixed_min_fraction: float = 0.15
    image_grid_threshold: int = 50
    image_grid_cells: int = 200


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


# Nguyên âm tiếng Việt precomposed trong Latin-1 (0xC0–0xFF) — HỢP LỆ, không tính là rác.
_VALID_VI_LATIN1 = frozenset("ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝàáâãèéêìíòóôõùúý")

# Ký tự "nghi legacy": toàn vùng 0x80–0xBF **cộng** mọi ký tự Latin-1 ở 0xC0–0xFF KHÔNG thuộc
# tiếng Việt (Ä Å Æ Ç Ë Î Ï Ð Ñ Ö Ø Û Ü Þ ß × ÷ … và chữ thường tương ứng). Mis-decode TCVN3/VNI
# đổ rất nhiều rác vào 0xC0–0xFF; chỉ loại trừ đúng các nguyên âm Việt hợp lệ nên không bắt nhầm
# chữ Việt Unicode. (Đ/đ = U+0110/0111 nằm ngoài Latin-1 → vẫn tính là chữ hợp lệ.)
_LEGACY_SUSPECT = frozenset(range(0x80, 0xC0)) | frozenset(
    cp for cp in range(0xC0, 0x100) if chr(cp) not in _VALID_VI_LATIN1
)


# Chữ Việt Unicode "thật": ký tự chỉ tồn tại trong Unicode đúng, mis-decode legacy không sinh ra.
# - Khối Latin Extended Additional phần tiếng Việt: U+1EA0–U+1EF9 (ạ ả ấ ầ … ỹ).
# - 8 chữ nền ngoài Latin-1: ă Ă đ Đ ơ Ơ ư Ư (U+0102/0103, U+0110/0111, U+01A0/01A1, U+01AF/01B0).
# (â ê ô à é… nằm trong Latin-1, cũng có trong tiếng Pháp → KHÔNG tính là "thật".)
_VI_UNICODE_LETTERS = frozenset("ăĂđĐơƠưƯ")


def has_real_vietnamese_unicode(text: str) -> bool:
    """True nếu ``text`` có ít nhất một ký tự tiếng Việt Unicode "thật" (xem ghi chú ở trên)."""
    for ch in text:
        if 0x1EA0 <= ord(ch) <= 0x1EF9 or ch in _VI_UNICODE_LETTERS:
            return True
    return False


def _legacy_counts(text: str) -> tuple[int, int]:
    """Đếm (số ký tự nghi legacy, số ký tự chữ-cái hợp lệ) — bỏ qua CJK/khoảng trắng/chữ số."""
    suspect = 0
    letters = 0
    for ch in text:
        if is_cjk(ch):
            continue
        if ord(ch) in _LEGACY_SUSPECT:
            suspect += 1
        elif ch.isalpha():
            letters += 1
    return suspect, letters


def legacy_char_ratio(text: str) -> float:
    """Tỷ lệ ký tự "nghi legacy" trên tổng ký tự chữ (loại CJK, khoảng trắng, chữ số).

    Mẫu số = số ký tự chữ-cái hợp lệ (không CJK) + số ký tự nghi. Tử số = số ký tự nghi.
    Văn bản Unicode sạch → ~0; văn bản TCVN3/VNI rút ra thành rác → cao.

    **Đây là heuristic low-recall để GẮN CỜ NGHI NGỜ**, không tuyệt đối: nó chỉ bắt được phần
    rác rơi ngoài tập nguyên âm Việt hợp lệ; nên hiệu chỉnh ``legacy_char_ratio_threshold`` theo
    sách thật ở SPIKE-0. Dấu còn lại (vd « » °) đôi khi dùng hợp lệ → dùng tỷ lệ + ngưỡng chữ tối
    thiểu.
    """
    suspect, letters = _legacy_counts(text)
    denom = suspect + letters
    if denom == 0:
        return 0.0
    return suspect / denom


def classify_span(font_name: str | None, text: str, config: DetectConfig) -> str:
    """Phân loại encoding của một span: **nội dung thắng tên font**, rồi tới heuristic ký tự.

    Nếu tên font khớp ``.Vn*``/``VNI-*`` NHƯNG span đủ dài và có chữ Việt Unicode thật thì text
    đã là Unicode đúng (font bị đổi tên / có ToUnicode) → ``text_unicode``. Tên font legacy vẫn
    được ghi riêng vào ``legacy_fonts`` ở ``detect_page`` để theo dõi.
    """
    suspect, letters = _legacy_counts(text)
    denom = suspect + letters
    by_name = classify_font_name(font_name)
    if by_name is not None:
        if letters >= config.legacy_min_chars and has_real_vietnamese_unicode(text):
            return TEXT_UNICODE
        return by_name
    if denom < config.legacy_min_chars:
        return TEXT_UNICODE  # span quá ngắn → không tin heuristic
    threshold = config.legacy_char_ratio_threshold
    # Tín hiệu mạnh (điểm 2): văn bản dài, có ký tự nghi, nhưng KHÔNG có chữ Việt Unicode thật →
    # nhiều khả năng mis-decode (chứ không phải tiếng Pháp/Anh, vốn ratio rất thấp) → hạ ngưỡng.
    if (
        letters >= config.legacy_long_text_chars
        and suspect > 0
        and not has_real_vietnamese_unicode(text)
    ):
        threshold = config.legacy_no_vi_ratio_threshold
    if suspect / denom >= threshold:
        return LEGACY_OTHER
    return TEXT_UNICODE


# --- Độ phủ ảnh & nhãn trang ---------------------------------------------------


_Rect = tuple[float, float, float, float]


def _normalize_rects(
    bboxes: list[tuple[float, float, float, float]],
    page_size: tuple[float, float] | None,
) -> list[_Rect]:
    """Chuẩn hóa (x0<x1, y0<y1), cắt về khung trang nếu biết, bỏ bbox rỗng."""
    rects: list[_Rect] = []
    for x0, y0, x1, y1 in bboxes:
        ax0, ax1 = (x0, x1) if x0 <= x1 else (x1, x0)
        ay0, ay1 = (y0, y1) if y0 <= y1 else (y1, y0)
        if page_size is not None:
            w, h = page_size
            ax0, ax1 = min(max(ax0, 0.0), w), min(max(ax1, 0.0), w)
            ay0, ay1 = min(max(ay0, 0.0), h), min(max(ay1, 0.0), h)
        if ax1 > ax0 and ay1 > ay0:
            rects.append((ax0, ay0, ax1, ay1))
    return rects


def _coverage_exact(rects: list[_Rect], page_area: float) -> float:
    """Diện tích union chính xác bằng nén tọa độ (dùng khi ít ảnh)."""
    xs = sorted({x for r in rects for x in (r[0], r[2])})
    ys = sorted({y for r in rects for y in (r[1], r[3])})
    covered = 0.0
    for i in range(len(xs) - 1):
        cx0, cx1 = xs[i], xs[i + 1]
        cxmid = (cx0 + cx1) / 2
        for j in range(len(ys) - 1):
            cy0, cy1 = ys[j], ys[j + 1]
            cymid = (cy0 + cy1) / 2
            if any(r[0] <= cxmid <= r[2] and r[1] <= cymid <= r[3] for r in rects):
                covered += (cx1 - cx0) * (cy1 - cy0)
    return min(1.0, covered / page_area)


def _coverage_grid(
    rects: list[_Rect],
    page_area: float,
    width: float,
    height: float,
    cells: int,
    early_stop_at: float | None,
) -> float:
    """Độ phủ xấp xỉ bằng lưới ``cells×cells`` ô (nhanh khi nhiều ảnh); dừng sớm khi vượt ngưỡng."""
    if width <= 0 or height <= 0:
        return 0.0
    cw, ch = width / cells, height / cells
    grid = bytearray(cells * cells)
    covered_cells = 0
    cell_area = cw * ch
    stop_cells = (
        None if early_stop_at is None else int(early_stop_at * page_area / cell_area)
    )
    for x0, y0, x1, y1 in rects:
        i0, i1 = max(0, int(x0 / cw)), min(cells - 1, int((x1 - 1e-9) / cw))
        j0, j1 = max(0, int(y0 / ch)), min(cells - 1, int((y1 - 1e-9) / ch))
        for i in range(i0, i1 + 1):
            base = i * cells
            for j in range(j0, j1 + 1):
                idx = base + j
                if not grid[idx]:
                    grid[idx] = 1
                    covered_cells += 1
        if stop_cells is not None and covered_cells >= stop_cells:
            break
    return min(1.0, covered_cells * cell_area / page_area)


def image_coverage(
    bboxes: list[tuple[float, float, float, float]],
    page_area: float,
    config: DetectConfig | None = None,
    *,
    page_size: tuple[float, float] | None = None,
    early_stop_at: float | None = None,
) -> float:
    """Tỷ lệ che phủ **hợp (union)** của các ảnh trên diện tích trang (0..1).

    Dùng union (không phải ảnh lớn nhất) để bắt scan bị cắt thành nhiều dải. Khi số ảnh vượt
    ``config.image_grid_threshold`` thì chuyển sang **lưới thô** (``image_grid_cells`` ô/chiều)
    cho nhanh, và **dừng sớm** khi đã vượt ``early_stop_at`` (dùng lúc phân loại scan). Nếu biết
    ``page_size`` thì cắt bbox về khung trang trước. An toàn khi ``page_area`` = 0.
    """
    if page_area <= 0:
        return 0.0
    config = config or DetectConfig()
    rects = _normalize_rects(bboxes, page_size)
    if not rects:
        return 0.0
    if len(rects) > config.image_grid_threshold:
        if page_size is not None:
            width, height = page_size
        else:
            width = max(r[2] for r in rects)
            height = max(r[3] for r in rects)
        return _coverage_grid(
            rects, page_area, width, height, config.image_grid_cells, early_stop_at
        )
    return _coverage_exact(rects, page_area)


def classify_page(
    spans: list[tuple[str | None, str]],
    char_count: int,
    image_coverage: float,
    config: DetectConfig,
) -> str:
    """Gộp các span thành một nhãn trang.

    Thứ tự quyết định:
    1. Trang ít chữ (``char_count < scan_min_chars``): ảnh phủ lớn → ``scan``, không → ``empty``.
    2. Đủ chữ **và** ảnh phủ ≥ ``scan_image_coverage`` → ``scan_ocr`` (ảnh scan + lớp text,
       thường là OCR). Tỷ lệ chữ ẩn được ghi riêng ở ``PageResult.hidden_text_ratio``.
    3. Còn lại: gộp encoding từng span (theo số ký tự không-trắng) → ``mixed`` nếu ≥ 2 loại mã
       cùng đáng kể, nếu không → loại chiếm ưu thế.
    """
    if char_count < config.scan_min_chars:
        return SCAN if image_coverage >= config.scan_image_coverage else EMPTY
    if image_coverage >= config.scan_image_coverage:
        return SCAN_OCR

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
    hidden_text_ratio: float = 0.0  # tỷ lệ ký tự ẩn (render mode 3) — gợi ý lớp OCR


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


def _page_image_coverage(page: fitz.Page, config: DetectConfig) -> float:
    rect = page.rect
    page_area = rect.width * rect.height
    try:
        infos = page.get_image_info()
    except Exception:
        return 0.0
    bboxes = [tuple(info["bbox"]) for info in infos if "bbox" in info]
    return image_coverage(
        bboxes,
        page_area,
        config,
        page_size=(rect.width, rect.height),
        early_stop_at=config.scan_image_coverage,
    )


def _hidden_text_ratio(page: fitz.Page) -> float:
    """Tỷ lệ ký tự vẽ ở render mode 3 (ẩn) — dấu hiệu lớp OCR nằm dưới ảnh scan.

    Dùng ``get_texttrace`` (mỗi span có ``type``; 3 = invisible). Không có API này → trả 0.0.
    """
    try:
        trace = page.get_texttrace()
    except Exception:
        return 0.0
    hidden = 0
    total = 0
    for span in trace:
        n = len(span.get("chars", ()))
        total += n
        if span.get("type") == 3:
            hidden += n
    return hidden / total if total else 0.0


def detect_page(page: fitz.Page, config: DetectConfig) -> PageResult:
    """Phân loại một trang PyMuPDF."""
    # Điểm 5: chỉ gọi get_text("dict") một lần; text trang dựng từ chính các span (nhất quán với
    # phần phân loại encoding, tránh hai nguồn trích khác nhau).
    spans = _page_spans(page)
    text = "\n".join(t for _, t in spans)
    char_count = _non_space_len(text)
    coverage = _page_image_coverage(page, config)
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
        hidden_text_ratio=_hidden_text_ratio(page),
    )


# Khi số trang hòa nhau, ưu tiên nhãn "cần xử lý" (legacy/scan/mixed) hơn text_unicode/empty,
# để một cuốn nửa-legacy không bị dán nhãn text_unicode rồi đi sai nhánh trích ở Mốc 1.
_BOOK_LABEL_PRIORITY = {
    LEGACY_TCVN3: 7,
    LEGACY_VNI: 6,
    LEGACY_OTHER: 5,
    SCAN: 4,  # scan thuần (chưa có text) cần OCR nhất
    SCAN_OCR: 3,  # scan nhưng đã có lớp text
    MIXED: 2,
    TEXT_UNICODE: 1,
    EMPTY: 0,
}


def _aggregate(path: str, pages: list[PageResult]) -> BookResult:
    distribution = dict(Counter(p.label for p in pages))
    # Nhãn cuốn = loại chiếm đa số; hòa số trang → chọn nhãn ưu tiên cao hơn (ổn định, có chủ đích).
    book_label = (
        max(
            distribution.items(),
            key=lambda kv: (kv[1], _BOOK_LABEL_PRIORITY.get(kv[0], -1)),
        )[0]
        if distribution
        else None
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
# Phần tên họ font sau mốc nhận dạng: cho phép chữ/số/khoảng trắng/`.`/`-`
# (vd ".Vn3DH", ".VnTime New", "VNI-Thuphap2"). Dùng fullmatch nên không cần neo ^$.
_FAMILY = r"[\w .-]*"

# TCVN3/ABC: tên bắt đầu bằng ".Vn" (dấu chấm có thể vắng ở vài bản), vd .VnTime, .VnArialH.
_TCVN3_RE = re.compile(rf"{_SUBSET}\.?Vn{_FAMILY}")
# VNI: bắt đầu bằng "VNI-", vd VNI-Times, VNI-Helve.
_VNI_RE = re.compile(rf"{_SUBSET}VNI-{_FAMILY}")


def classify_font_name(font_name: str | None) -> str | None:
    """Phân loại font cũ theo **tên span**, có xử lý tiền tố subset ``ABCDEF+``.

    Trả ``legacy_tcvn3`` / ``legacy_vni`` nếu khớp mẫu đã biết; ``None`` nếu tên sạch
    (vd ``TimesNewRomanPSMT``, ``ArialMT``). Dùng ``fullmatch`` để tránh dương tính giả
    (font sạch có chuỗi con giống mẫu sẽ không bị khớp). VPS/VISCII chưa có mẫu tên tin
    cậy nên không nhận ở đây — dựa vào heuristic ký tự (``legacy_char_ratio``).
    """
    if not font_name:
        return None
    if _TCVN3_RE.fullmatch(font_name):
        return LEGACY_TCVN3
    if _VNI_RE.fullmatch(font_name):
        return LEGACY_VNI
    return None
