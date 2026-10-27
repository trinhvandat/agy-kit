"""Route **scan_ocr hybrid** — bố cục Docling + chữ Apple Vision (từ cache) theo toạ độ.

Vì sao (SPIKE-5, ADR-009): Docling cho **bố cục** tốt (reading-order nhiều cột, cắt hình), nhưng
nếu để Docling tự OCR bằng Vision thì chữ **tệ ~10×**. Giải pháp: Docling chỉ lấy **khối + bbox +
thứ tự đọc** (``do_ocr=False``), còn **chữ** lấy từ **cache Vision** (:mod:`ocr_vision` →
:mod:`ocr_cache`) bằng cách **gán mỗi dòng Vision vào khối Docling chồng lấn nhiều nhất** (theo
diện tích). Kết quả ≈ chất lượng Vision raw + giữ bố cục Docling (SPIKE-5: WER ~4.5%).

Không OCR ở đây — chỉ đọc cache → route này chạy **tất định** (và test được trên CI không-Vision).
Cần extra ``docling`` để lấy bố cục.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .docling_adapter import (
    _caption_text,
    _label,
    _page_no,
    _png_of,
    docling_available,
)
from .model import Block, Heading, ImageBlock, Paragraph, Table
from .ocr_cache import BBox, OcrCache, OcrLine
from .reflow import normalize_text

_HEADING_LABELS = {"section_header", "title"}
_PARA_LABELS = {"text", "paragraph", "list_item", "footnote", "code", "formula"}
_SKIP_LABELS = {"page_header", "page_footer"}

# Dòng Vision phủ ≥ ngưỡng này diện tích của nó vào một khối → coi là "thuộc" khối đó.
_MIN_OVERLAP = 0.2
# Picture có ≥ ngưỡng ký tự Vision gán vào → coi là KHUNG CHỮ (xuất đoạn), ít hơn → ảnh + caption.
TEXT_IN_PICTURE_MIN_CHARS = 80


@dataclass(frozen=True)
class HybridReport:
    """Thống kê route hybrid (đưa vào cảnh báo convert)."""

    vision_lines: int = 0
    assigned_lines: int = 0
    cross_block_lines: int = (
        0  # dòng Vision chồng ≥2 khối (nghi gộp cột) → gán theo chồng lấn lớn nhất
    )
    floating_lines: int = 0  # dòng không chồng khối nào → gán khối gần nhất (fallback)
    fallback_pages: tuple[int, ...] = ()  # trang KHÔNG có cache → giữ chữ Docling/ABBYY
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _non_space_len(text: str) -> int:
    return sum(1 for ch in text if not ch.isspace())


def _norm_bbox(item, page_w: float, page_h: float) -> BBox | None:
    """Bbox khối Docling → chuẩn hoá trên-trái [x0,y0,x1,y1] ∈ [0,1]; ``None`` nếu thiếu toạ độ."""
    prov = getattr(item, "prov", None)
    if not prov or page_w <= 0 or page_h <= 0:
        return None
    bb = prov[0].bbox
    try:
        tl = bb.to_top_left_origin(page_height=page_h)
        left, top, right, bot = tl.l, tl.t, tl.r, tl.b
    except Exception:
        left, top, right, bot = bb.l, page_h - bb.t, bb.r, page_h - bb.b
    x0, x1 = sorted((left / page_w, right / page_w))
    y0, y1 = sorted((top / page_h, bot / page_h))
    return (x0, y0, x1, y1)


def _overlap_frac(line: BBox, block: BBox) -> float:
    """Phần diện tích của **dòng** nằm trong **khối** (0..1)."""
    ix = max(0.0, min(line[2], block[2]) - max(line[0], block[0]))
    iy = max(0.0, min(line[3], block[3]) - max(line[1], block[1]))
    line_area = (line[2] - line[0]) * (line[3] - line[1])
    return (ix * iy) / line_area if line_area > 0 else 0.0


def _center_dist2(line: BBox, block: BBox) -> float:
    lx, ly = (line[0] + line[2]) / 2, (line[1] + line[3]) / 2
    bx, by = (block[0] + block[2]) / 2, (block[1] + block[3]) / 2
    return (lx - bx) ** 2 + (ly - by) ** 2


def _area(b: BBox) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


@dataclass
class _Target:
    """Một khối Docling nhận chữ Vision."""

    order: int
    page: int  # 1-based (Docling)
    label: str
    bbox: BBox
    level: int
    item: object  # item Docling gốc (để lấy ảnh/caption nếu là picture)
    lines: list[OcrLine] = field(default_factory=list)


def _assign_lines(
    targets: list[_Target], lines_by_page: dict[int, list[OcrLine]]
) -> tuple[int, int, int]:
    """Gán dòng Vision vào target theo chồng lấn. Trả (assigned, cross_block, floating)."""
    by_page: dict[int, list[_Target]] = {}
    for t in targets:
        by_page.setdefault(t.page, []).append(t)
    assigned = cross = floating = 0
    for t_page, tgts in by_page.items():
        for line in lines_by_page.get(t_page - 1, []):  # cache 0-based
            cands = [(t, _overlap_frac(line.bbox, t.bbox)) for t in tgts]
            cands = [(t, ov) for t, ov in cands if ov >= _MIN_OVERLAP]
            if cands:
                # Gán vào khối NHỎ NHẤT trong số chồng lấn đủ (đặc trưng nhất) — tránh nuốt dòng
                # nhãn vào khối "picture" to bao quanh (lỗi gộp cột trên trang có sơ đồ).
                best = min(cands, key=lambda c: _area(c[0].bbox))[0]
                best_area = _area(best.bbox)
                # Vắt cột THẬT: có khối SIBLING (diện tích ≤ 3× khối nhỏ nhất, không phải khung bao)
                # cũng chồng đủ → nghi dòng vắt qua 2 cột.
                if sum(1 for t, _ in cands if _area(t.bbox) <= 3 * best_area) >= 2:
                    cross += 1
                best.lines.append(line)
                assigned += 1
            else:  # không chồng khối nào đáng kể → gán khối gần nhất (giữ chữ, không mất độ phủ)
                nearest = min(tgts, key=lambda t: _center_dist2(line.bbox, t.bbox))
                nearest.lines.append(line)
                floating += 1
    return assigned, cross, floating


def _target_text(t: _Target) -> tuple[str, float | None]:
    """Chữ của target = các dòng Vision gán vào, **GIỮ thứ tự Vision gốc** (text_NFC, conf_min).

    KHÔNG sắp lại theo (y, x): khi Docling gộp cả sơ đồ + nhiều nhãn vào MỘT khối ``picture`` (trang
    có hình), sắp theo y sẽ **trộn các cột nhãn** (quét ngang qua trang) → hỏng thứ tự đọc. Thứ tự
    Vision gốc (đã lưu trong cache) xử lý nhiều cột tốt hơn hẳn (SPIKE-5: WER p101 2% ở thứ tự gốc
    vs ~29% khi sắp theo y). Đoạn thường thì thứ tự Vision gốc = trên→dưới nên không hại.
    """
    if not t.lines:
        return "", None
    text = normalize_text(" ".join(ln.text for ln in t.lines))
    conf = min(ln.confidence for ln in t.lines)
    return text, conf


def _build_converter(image_scale: float):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions()
    opts.do_ocr = False  # chỉ lấy BỐ CỤC; chữ lấy từ cache Vision
    opts.generate_picture_images = True
    opts.images_scale = image_scale
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )


def extract_blocks_hybrid(
    pdf_path: str | Path,
    cache: OcrCache,
    *,
    image_scale: float = 2.0,
    text_in_picture_min_chars: int = TEXT_IN_PICTURE_MIN_CHARS,
) -> tuple[list[Block], HybridReport]:
    """Trích ``pdf_path`` = **bố cục Docling + chữ Vision (từ ``cache``)**. Cần extra docling.

    Thứ tự đọc theo Docling; mỗi khối chữ lấy text từ dòng Vision chồng lấn nó; picture nhiều chữ
    Vision → khung chữ (đoạn), ít chữ → ảnh + caption. Trả ``(blocks, HybridReport)``.
    """
    if not docling_available():
        from .docling_adapter import INSTALL_HINT

        raise RuntimeError(INSTALL_HINT)
    conv = _build_converter(image_scale)
    doc = conv.convert(str(pdf_path)).document

    page_size: dict[int, tuple[float, float]] = {}
    for pno, page in getattr(doc, "pages", {}).items():
        size = getattr(page, "size", None)
        if size is not None:
            page_size[pno] = (float(size.width), float(size.height))

    # 1) Thu các khối theo thứ tự đọc; khối chữ/picture có bbox → target nhận chữ Vision.
    order_items: list[dict] = []
    targets: list[_Target] = []
    for item, _lvl in doc.iterate_items():
        label = _label(item)
        if label in _SKIP_LABELS:
            continue
        page = _page_no(item)
        w, h = page_size.get(page, (0.0, 0.0))
        bbox = _norm_bbox(item, w, h)
        entry = {"item": item, "label": label, "page": page, "bbox": bbox, "target": None}
        if label in _HEADING_LABELS and bbox is not None:
            level = 1 if label == "title" else max(1, min(3, int(getattr(item, "level", 2) or 2)))
            t = _Target(len(targets), page, label, bbox, level, item)
            targets.append(t)
            entry["target"] = t
        elif (label in _PARA_LABELS or label == "caption") and bbox is not None:
            t = _Target(len(targets), page, label, bbox, 0, item)
            targets.append(t)
            entry["target"] = t
        elif label == "picture" and bbox is not None:
            t = _Target(len(targets), page, "picture", bbox, 0, item)
            targets.append(t)
            entry["target"] = t
        order_items.append(entry)

    # 2) Gán dòng Vision vào target theo chồng lấn.
    lines_by_page = {p.page: list(p.lines) for p in cache.pages}
    assigned, cross, floating = _assign_lines(targets, lines_by_page)
    cached_pages = set(lines_by_page)
    fallback_pages = tuple(
        sorted({e["page"] - 1 for e in order_items if (e["page"] - 1) not in cached_pages})
    )

    # 3) Dựng blocks theo thứ tự Docling; chữ từ Vision (fallback Docling nếu trang thiếu cache).
    blocks: list[Block] = []
    for e in order_items:
        item, label, page, t = e["item"], e["label"], e["page"], e["target"]
        if label in _HEADING_LABELS:
            text, conf = _target_text(t) if t else ("", None)
            if not text:
                text = normalize_text(getattr(item, "text", "") or "")
            if text:
                blocks.append(Heading(text=text, level=t.level, page=page, confidence=conf))
        elif label in _PARA_LABELS:
            text, conf = _target_text(t) if t else ("", None)
            if not text:
                text = normalize_text(getattr(item, "text", "") or "")
            if not text:
                continue
            if label == "list_item":
                text = f"• {text}"
            blocks.append(Paragraph(text=text, page=page, confidence=conf))
        elif label == "picture":
            text, conf = _target_text(t) if t else ("", None)
            if _non_space_len(text) >= text_in_picture_min_chars:
                blocks.append(Paragraph(text=text, page=page, confidence=conf))
            else:
                png = _png_of(item, doc)
                if png is None:
                    continue
                caption = text or _caption_text(item, doc)
                blocks.append(ImageBlock(png=png, page=page, caption=caption))
        elif label == "table":
            from .docling_adapter import _table_rows

            rows = _table_rows(item)
            if rows:
                blocks.append(Table(rows=rows, page=page))
        elif label == "caption":
            text, _conf = _target_text(t) if t else ("", None)
            if not text:
                text = normalize_text(getattr(item, "text", "") or "")
            if text and blocks and isinstance(blocks[-1], ImageBlock) and not blocks[-1].caption:
                prev = blocks[-1]
                blocks[-1] = ImageBlock(png=prev.png, page=prev.page, caption=text)
            elif text:
                blocks.append(Paragraph(text=text, page=page))

    warnings: list[str] = []
    if cross:
        warnings.append(
            f"{cross} dòng Vision chồng ≥2 khối (nghi gộp cột) — gán theo chồng lấn lớn nhất"
        )
    if fallback_pages:
        warnings.append(
            f"{len(fallback_pages)} trang không có cache OCR → giữ chữ Docling (ABBYY): "
            f"{list(fallback_pages[:10])}{'…' if len(fallback_pages) > 10 else ''}"
        )
    report = HybridReport(
        vision_lines=sum(len(v) for v in lines_by_page.values()),
        assigned_lines=assigned,
        cross_block_lines=cross,
        floating_lines=floating,
        fallback_pages=fallback_pages,
        warnings=tuple(warnings),
    )
    return blocks, report
