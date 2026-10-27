"""Cache OCR (Apple Vision) — **đọc/ghi thuần stdlib**, KHÔNG phụ thuộc Vision/macOS.

Vì sao tách riêng: OCR Apple Vision chỉ chạy trên macOS lúc **ingest một lần** (xem
:mod:`ocr_vision`). Kết quả được lưu thành **cache trên đĩa**; mọi bước sau (``convert``, test CI
trên Ubuntu) **chỉ đọc cache** — nên module này không import ocrmac/pymupdf và chạy ở mọi nơi.

Cache **tất định**: text NFC, toạ độ làm tròn, JSON ``sort_keys`` → ghi 2 lần byte-identical, diff
được. Khoá theo **SHA-256 PDF gốc** (= ``bookUid``) + **engine** + **phiên bản macOS/Vision**
(``engine_version``): cache của phiên bản khác → coi là *mismatch* (không âm thầm dùng OCR phiên bản
khác). Thiết kế: docs/spikes/spike-5-reocr-vision.md "Thiết kế tất định"; ADR-009 (docs/05).
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

OCR_SCHEMA = 1  # tăng khi đổi cấu trúc cache (bất tương thích)

# Mô tả engine + tham số render (đi vào khoá cache). Đặt ở module stdlib này để ``convert`` kiểm
# cache được mà KHÔNG import tầng Vision (ocrmac). ``ocr_vision`` dùng lại hằng số này khi OCR.
OCR_RENDER = {"dpi": 300}
OCR_ENGINE = {
    "name": "apple-vision",
    "recognition": "accurate",
    "lang": ["vi-VT"],
    "framework": "vision",
}

# Thư mục cache mặc định: cạnh pipeline (không cạnh app — ADR-004 pipeline tách rời).
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / ".ocr_cache"

BBox = tuple[float, float, float, float]  # (x0, y0, x1, y1) CHUẨN HOÁ [0,1], gốc trên-trái


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


@dataclass(frozen=True)
class OcrLine:
    """Một dòng Vision nhận được: text (NFC) + bbox chuẩn hoá (trên-trái) + độ tin."""

    text: str
    bbox: BBox  # x0,y0,x1,y1 ∈ [0,1], gốc trên-trái
    confidence: float

    def to_dict(self) -> dict:
        x0, y0, x1, y1 = self.bbox
        return {
            "text": _nfc(self.text),
            "bbox": [round(x0, 6), round(y0, 6), round(x1, 6), round(y1, 6)],
            "conf": round(float(self.confidence), 4),
        }

    @staticmethod
    def from_dict(d: dict) -> OcrLine:
        b = d["bbox"]
        return OcrLine(text=_nfc(d["text"]), bbox=(b[0], b[1], b[2], b[3]), confidence=d["conf"])


@dataclass(frozen=True)
class OcrPage:
    """OCR của một trang (``page`` = chỉ số trang 0-based trong PDF)."""

    page: int
    lines: tuple[OcrLine, ...] = ()

    def to_dict(self) -> dict:
        return {"page": self.page, "lines": [ln.to_dict() for ln in self.lines]}

    @staticmethod
    def from_dict(d: dict) -> OcrPage:
        return OcrPage(page=int(d["page"]), lines=tuple(OcrLine.from_dict(x) for x in d["lines"]))


@dataclass(frozen=True)
class OcrCache:
    """Toàn bộ OCR của một cuốn, cùng khoá định danh (xem module docstring)."""

    book_uid: str
    pdf_sha256: str
    render: dict  # {"dpi": 300}
    engine: dict  # {"name","recognition","lang","framework"}
    engine_version: dict  # {"macos_build","macos_ver","vision_langs_sha","ocrmac"}
    created: str  # ngày ISO (YYYY-MM-DD)
    pages: tuple[OcrPage, ...] = ()
    ocr_schema: int = OCR_SCHEMA

    @property
    def n_lines(self) -> int:
        return sum(len(p.lines) for p in self.pages)

    def to_dict(self) -> dict:
        return {
            "ocr_schema": self.ocr_schema,
            "book_uid": self.book_uid,
            "pdf_sha256": self.pdf_sha256,
            "render": self.render,
            "engine": self.engine,
            "engine_version": self.engine_version,
            "created": self.created,
            "pages": [p.to_dict() for p in self.pages],
        }

    @staticmethod
    def from_dict(d: dict) -> OcrCache:
        return OcrCache(
            book_uid=d["book_uid"],
            pdf_sha256=d["pdf_sha256"],
            render=d["render"],
            engine=d["engine"],
            engine_version=d["engine_version"],
            created=d["created"],
            pages=tuple(OcrPage.from_dict(p) for p in d["pages"]),
            ocr_schema=int(d.get("ocr_schema", OCR_SCHEMA)),
        )


def _canonical(obj: dict) -> str:
    """JSON tất định (sort_keys, không ASCII-escape) — để tính khoá + ghi file diff được."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)


def cache_key(pdf_sha256: str, render: dict, engine: dict, engine_version: dict) -> str:
    """Khoá nội dung của một lần OCR cụ thể (SHA-256 của bộ định danh)."""
    payload = _canonical(
        {
            "pdf_sha256": pdf_sha256,
            "render": render,
            "engine": engine,
            "engine_version": engine_version,
        }
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cache_path(cache_dir: str | Path, pdf_sha256: str) -> Path:
    """Đường dẫn file cache của một cuốn: ``<cache_dir>/<pdf_sha256>.json``."""
    return Path(cache_dir) / f"{pdf_sha256}.json"


def write_cache(cache: OcrCache, cache_dir: str | Path) -> Path:
    """Ghi cache (tất định). Trả đường dẫn file."""
    path = cache_path(cache_dir, cache.pdf_sha256)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_canonical(cache.to_dict()) + "\n", encoding="utf-8")
    return path


def read_cache(cache_dir: str | Path, pdf_sha256: str) -> OcrCache | None:
    """Đọc cache của một cuốn nếu có; ``None`` nếu không có file."""
    path = cache_path(cache_dir, pdf_sha256)
    if not path.exists():
        return None
    return OcrCache.from_dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class CacheStatus:
    """Trạng thái cache so với engine/phiên bản ĐANG cấu hình."""

    state: str  # "hit" | "miss" | "mismatch"
    reason: str = ""
    cache: OcrCache | None = field(default=None, repr=False)

    @property
    def ok(self) -> bool:
        return self.state == "hit"


def cache_status(
    cache_dir: str | Path,
    pdf_sha256: str,
    expected_engine: dict,
    expected_version: dict,
) -> CacheStatus:
    """Tra cache cho cuốn + kiểm khớp engine/phiên bản.

    - không có file → ``miss``.
    - có file nhưng ``engine``/``engine_version``/``schema`` khác cấu hình → ``mismatch`` (KHÔNG
      âm thầm dùng OCR phiên bản/engine khác — giữ tất định; cần OCR lại).
    - khớp hết → ``hit`` (kèm ``cache``).
    """
    cache = read_cache(cache_dir, pdf_sha256)
    if cache is None:
        return CacheStatus("miss", "chưa có cache OCR cho cuốn này")
    if cache.ocr_schema != OCR_SCHEMA:
        return CacheStatus("mismatch", f"schema cache {cache.ocr_schema} ≠ {OCR_SCHEMA}")
    if cache.engine != expected_engine:
        return CacheStatus("mismatch", "engine trong cache khác engine đang cấu hình")
    if cache.engine_version != expected_version:
        return CacheStatus(
            "mismatch",
            f"engine_version khác (cache: {cache.engine_version.get('macos_build')} / "
            f"hiện tại: {expected_version.get('macos_build')})",
        )
    return CacheStatus("hit", f"{len(cache.pages)} trang, {cache.n_lines} dòng", cache)
