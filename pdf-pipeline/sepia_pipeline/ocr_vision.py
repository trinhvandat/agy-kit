"""OCR lại sách scan bằng **Apple Vision** (ingest một lần) → :class:`ocr_cache.OcrCache`.

CHỈ chạy trên **macOS** với extra ``ocr-mac`` (gói ``ocrmac``, pyobjc). Vì sao ocrmac (không phải
Swift helper): không cần biên dịch, cùng chất lượng (SPIKE-5: cả hai ~2% WER), và trả **text + bbox
chuẩn hoá + độ tin** sẵn — đúng thứ cache cần. Vì sao KHÔNG để Docling gọi Vision: SPIKE-5 cho thấy
Docling+OcrMac làm chữ tệ ~10× (lỗi trong khâu OCR nội bộ Docling), nên ta render + OCR cả trang
trực tiếp ở đây và chỉ mượn *bố cục* của Docling ở route hybrid (PIPELINE_VERSION 5).

Kết quả **không** dùng ngay trong ``convert``; nó được ghi cache (:mod:`ocr_cache`) rồi build EPUB
đọc từ cache → tất định, chạy được CI không-Vision.
"""

from __future__ import annotations

import datetime
import hashlib
import importlib.metadata
import importlib.util
import platform
import subprocess
from io import BytesIO
from pathlib import Path

import pymupdf as fitz

from .extract import sha256_file
from .ocr_cache import OCR_ENGINE, OCR_RENDER, OcrCache, OcrLine, OcrPage

__all__ = ["OCR_ENGINE", "OCR_RENDER", "ocr_available", "ocr_pdf", "engine_version", "INSTALL_HINT"]

INSTALL_HINT = (
    "OCR Apple Vision cần macOS + extra `ocr-mac`. Cài trên Mac: `uv sync --extra ocr-mac`."
)


def ocr_available() -> bool:
    """True nếu đã cài ``ocrmac`` (extra ``ocr-mac``, chỉ có trên macOS)."""
    return importlib.util.find_spec("ocrmac") is not None


def _sw_vers(flag: str) -> str:
    try:
        return subprocess.run(
            ["sw_vers", flag], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return ""


def engine_version() -> dict:
    """Vân tay môi trường OCR — đổi macOS/Vision/ocrmac ⇒ đổi ⇒ cache cũ thành *mismatch*.

    Gồm: bản macOS + build, SHA của **danh sách ngôn ngữ Vision hỗ trợ** (đại diện cho phiên bản
    model Vision), và phiên bản ``ocrmac``. Cần Vision ⇒ chỉ gọi được trên Mac có extra.
    """
    import ocrmac  # noqa: F401  (xác nhận có extra)
    import Vision

    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(0)  # accurate
    langs, _err = req.supportedRecognitionLanguagesAndReturnError_(None)
    langs_sha = hashlib.sha256("|".join(str(x) for x in (langs or [])).encode()).hexdigest()[:12]
    return {
        "macos_ver": platform.mac_ver()[0] or _sw_vers("-productVersion"),
        "macos_build": _sw_vers("-buildVersion"),
        "vision_langs_sha": langs_sha,
        "ocrmac": importlib.metadata.version("ocrmac"),
    }


def _ocr_image(pil_image) -> list[OcrLine]:
    """OCR một ảnh PIL bằng Vision (vi-VT, accurate) → dòng + bbox trên-trái chuẩn hoá + độ tin."""
    from ocrmac import ocrmac

    result = ocrmac.OCR(
        pil_image,
        framework=OCR_ENGINE["framework"],
        recognition_level=OCR_ENGINE["recognition"],
        language_preference=OCR_ENGINE["lang"],
    ).recognize()
    lines: list[OcrLine] = []
    for text, conf, (x, y, w, h) in result:
        # ocrmac trả bbox chuẩn hoá gốc DƯỚI-trái (x,y,w,h). Quy về TRÊN-trái [x0,y0,x1,y1].
        lines.append(OcrLine(text=text, bbox=(x, 1.0 - (y + h), x + w, 1.0 - y), confidence=conf))
    return lines


def ocr_pdf(
    pdf_path: str | Path,
    *,
    dpi: int = 300,
    pages: list[int] | None = None,
    created: str | None = None,
) -> OcrCache:
    """Render từng trang ``pdf_path`` → OCR Vision → :class:`OcrCache` (CHƯA ghi đĩa).

    ``pages`` = danh sách chỉ số 0-based cần OCR (mặc định: cả cuốn). Cần macOS + extra ``ocr-mac``.
    """
    if not ocr_available():
        raise RuntimeError(INSTALL_HINT)
    from PIL import Image

    pdf_path = Path(pdf_path)
    sha = sha256_file(pdf_path)
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    doc = fitz.open(str(pdf_path))
    try:
        page_idx = pages if pages is not None else list(range(doc.page_count))
        ocr_pages: list[OcrPage] = []
        for pi in page_idx:
            png = doc[pi].get_pixmap(matrix=mat).tobytes("png")
            pil = Image.open(BytesIO(png)).convert("RGB")
            ocr_pages.append(OcrPage(page=pi, lines=tuple(_ocr_image(pil))))
    finally:
        doc.close()

    return OcrCache(
        book_uid=f"sepia:{sha}",
        pdf_sha256=sha,
        render={"dpi": dpi},
        engine=dict(OCR_ENGINE),
        engine_version=engine_version(),
        created=created or datetime.date.today().isoformat(),
        pages=tuple(ocr_pages),
    )
