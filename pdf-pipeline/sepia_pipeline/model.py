"""Mô hình trung gian (PDF → model → EPUB).

Các bước sau (reflow/toc/build_epub) làm việc trên mô hình **bất biến** này, **không** đụng
PyMuPDF — nhờ vậy test được mà không cần file PDF thật (giống cách ``detect.py`` tách hàm thuần).
``extract.py`` là lớp mỏng bọc PyMuPDF để dựng nên các dataclass ở đây.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BBox = tuple[float, float, float, float]  # (x0, y0, x1, y1), gốc tọa độ góc trên-trái


def _non_space_len(text: str) -> int:
    return sum(1 for ch in text if not ch.isspace())


@dataclass(frozen=True)
class TextSpan:
    """Một run chữ cùng font/cỡ/kiểu (đơn vị nhỏ nhất PyMuPDF trả về)."""

    text: str
    font: str
    size: float
    bold: bool = False
    italic: bool = False


@dataclass(frozen=True)
class Line:
    """Một dòng văn bản: nhiều span + bbox + số trang (1-based)."""

    page: int
    bbox: BBox
    spans: tuple[TextSpan, ...]

    @property
    def text(self) -> str:
        """Nối text các span (không thêm khoảng trắng — span đã chứa khoảng trắng của nó)."""
        return "".join(s.text for s in self.spans)

    @property
    def char_count(self) -> int:
        return _non_space_len(self.text)

    @property
    def y0(self) -> float:
        return self.bbox[1]

    @property
    def y1(self) -> float:
        return self.bbox[3]

    @property
    def x0(self) -> float:
        return self.bbox[0]

    @property
    def dominant_size(self) -> float:
        """Cỡ chữ theo span có **nhiều ký tự nhất** (0.0 nếu dòng rỗng)."""
        best_size = 0.0
        best_weight = -1
        for s in self.spans:
            w = _non_space_len(s.text)
            if w > best_weight:
                best_weight, best_size = w, s.size
        return best_size

    @property
    def is_bold(self) -> bool:
        """True nếu mọi span có chữ đều đậm."""
        spans = [s for s in self.spans if _non_space_len(s.text)]
        return bool(spans) and all(s.bold for s in spans)


@dataclass(frozen=True)
class Page:
    """Một trang: các dòng (đã sắp thứ tự đọc) + kích thước + cờ ảnh.

    ``image_png`` khác ``None`` nghĩa là trang này được render nguyên trang thành PNG (trang ảnh,
    US-A6); khi đó ``lines`` thường rỗng/ít và không dùng để reflow.
    """

    number: int  # 1-based
    width: float
    height: float
    lines: tuple[Line, ...] = ()
    image_coverage: float = 0.0
    has_full_page_image: bool = False
    image_png: bytes | None = None

    @property
    def char_count(self) -> int:
        return sum(ln.char_count for ln in self.lines)

    @property
    def is_image_page(self) -> bool:
        return self.image_png is not None


# --- Khối ngữ nghĩa sau reflow (đầu vào cho build_epub) ------------------------


@dataclass(frozen=True)
class Heading:
    """Tiêu đề (level 1..3) → ``<h1>/<h2>/<h3>`` + mục trong nav.

    ``top_ratio`` = vị trí dọc mép trên khối / chiều cao trang (gốc trên-trái, 0 = sát mép trên).
    Chỉ đường Docling ghi (từ ``prov[0].bbox``); đường heuristic để ``None``. Dùng để chặn
    :func:`reflow.drop_running_headers` chỉ bỏ tiêu đề chạy nằm trong **dải mép trên**.
    """

    text: str
    level: int
    page: int
    top_ratio: float | None = None
    confidence: float | None = (
        None  # độ tin OCR (route hybrid); KHÔNG xuất EPUB — dành đánh dấu sau
    )


@dataclass(frozen=True)
class Paragraph:
    """Một đoạn văn đã ghép dòng → ``<p>``.

    ``top_ratio``: xem :class:`Heading` (chỉ đường Docling ghi; heuristic để ``None``).
    ``confidence``: độ tin OCR thấp nhất của các dòng Vision gộp vào (route hybrid); ``None`` nếu
    không từ OCR. **Chỉ dùng nội bộ** — build_epub KHÔNG xuất ra EPUB (dành cho việc đánh dấu chữ
    không chắc về sau).
    """

    text: str
    page: int
    top_ratio: float | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class ImageBlock:
    """Ảnh (trang ảnh US-A6 hoặc hình do Docling cắt) → ``<figure><img>`` + ``<figcaption>``."""

    png: bytes
    page: int
    caption: str = ""


@dataclass(frozen=True)
class Table:
    """Bảng (chủ yếu do Docling nhận dạng) → ``<table>``. ``rows`` là các hàng ô text."""

    rows: tuple[tuple[str, ...], ...]
    page: int


Block = Heading | Paragraph | ImageBlock | Table


@dataclass(frozen=True)
class Document:
    """Cả cuốn: trang + metadata + định danh ổn định (``pdf_sha256`` → bookUid)."""

    pages: tuple[Page, ...]
    source_pdf_name: str
    pdf_sha256: str
    title: str | None = None
    author: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def book_uid(self) -> str:
        """Định danh sách ổn định ghi vào ``dc:identifier`` (docs/04 §6)."""
        return f"sepia:{self.pdf_sha256}"
