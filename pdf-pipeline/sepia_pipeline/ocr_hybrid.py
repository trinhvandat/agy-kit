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

import re
import unicodedata
from collections import Counter
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
from .reflow import collapse_ws, is_page_number_line, normalize_text

_HEADING_LABELS = {"section_header", "title"}
_PARA_LABELS = {"text", "paragraph", "list_item", "footnote", "code", "formula"}
_SKIP_LABELS = {"page_header", "page_footer"}

# Dòng Vision phủ ≥ ngưỡng này diện tích của nó vào một khối → coi là "thuộc" khối đó.
_MIN_OVERLAP = 0.2
# Picture có ≥ ngưỡng ký tự Vision gán vào → coi là KHUNG CHỮ (xuất đoạn), ít hơn → ảnh + caption.
TEXT_IN_PICTURE_MIN_CHARS = 80

# --- "Đồ đạc" trang (furniture): tiêu đề chạy + số trang — bỏ theo bbox DÒNG VISION (Việc 1) ---
# Vì sao ở đây (không dùng reflow.drop_running_headers): route hybrid dựng khối từ bố cục Docling,
# khối Heading/Paragraph **không mang** ``top_ratio`` → drop_running_headers (xét top_ratio) không
# bao giờ chạy. Dòng Vision trong cache LẠI có bbox chuẩn hoá chính xác → bỏ furniture ngay ở mức
# dòng, TRƯỚC khi gán vào khối (nên không lọt vào thân bài, không tạo đoạn trôi).
#
# dải mép = 0.08 (gốc trên-trái): nhãn mục thật trong sách tra cứu ("Tên gọi:", "LẤY HUYỆT") nằm ở
# top_ratio 0.10–0.17 (spike-4 §v4) → ngoài dải, không bị bỏ nhầm. Ngưỡng LẶP tuyệt đối ≥ 3 trang
# (KHÔNG theo tỷ lệ %): trên sách mẫu 292 trang, OCR làm vỡ tiêu đề chạy thành nhiều biến thể, mỗi
# biến thể < 10% số trang — ngưỡng theo % (vd 20%) bỏ sót tất cả. Một dòng ở **mép** trang lặp trên
# ≥ 3 trang gần như chắc chắn là đồ đạc, bất kể sách dài bao nhiêu.
FURNITURE_BAND_RATIO = 0.08
FURNITURE_MIN_PAGES = 3
FURNITURE_KEY_WORDS = 2  # khoá = 2 từ-chữ đầu → gộp biến thể OCR chỉ khác phần đuôi
FURNITURE_MIN_LETTERS = 4  # dòng quá ít chữ cái → không làm khoá (để pass ký hiệu lo)

_LETTER_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def _letters_len(text: str) -> int:
    return sum(1 for ch in text if ch.isalpha())


def _furniture_key(text: str, n_words: int = FURNITURE_KEY_WORDS) -> str:
    """Khoá so khớp đồ đạc: NFC + hạ thường, bỏ chữ số, lấy ``n_words`` **từ-chữ đầu**.

    Gộp biến thể OCR chỉ khác phần ĐUÔI (vd "...Cứu mối ngải" / "...Cứu mỗi ngài") về một khoá, và
    bỏ **từ một-chữ-cái dẫn đầu** (rác máng lề OCR: "J Chương…", "/ Chương…") để không tách khoá.
    """
    t = unicodedata.normalize("NFC", text).lower()
    t = re.sub(r"\d+", "", t)
    words = _LETTER_WORD_RE.findall(t)
    while words and len(words[0]) == 1:  # bỏ chữ-cái-đơn dẫn đầu (rác OCR)
        words.pop(0)
    return " ".join(words[:n_words])


def _in_band(bbox: BBox, band_ratio: float) -> bool:
    _x0, y0, _x1, y1 = bbox
    return y0 < band_ratio or y1 > 1 - band_ratio


@dataclass(frozen=True)
class FurnitureResult:
    """Kết quả bỏ đồ đạc trang: dòng giữ theo trang, số dòng bỏ, danh sách đồ đạc (duy nhất)."""

    kept_by_page: dict[int, list[OcrLine]]
    removed: int
    examples: tuple[str, ...]  # "text (×số trang)" cho mỗi đồ đạc duy nhất (nhiều→ít)


def detect_furniture(
    lines_by_page: dict[int, list[OcrLine]],
    *,
    band_ratio: float = FURNITURE_BAND_RATIO,
    min_pages: int = FURNITURE_MIN_PAGES,
    n_words: int = FURNITURE_KEY_WORDS,
    min_letters: int = FURNITURE_MIN_LETTERS,
) -> FurnitureResult:
    """Bỏ **tiêu đề chạy + số trang** khỏi các dòng Vision, theo bbox dòng (xem khối docstring).

    Ứng viên = dòng trong **dải mép** (trên ``band_ratio`` hoặc dưới ``1-band_ratio``). Dòng **số
    trang** ("12", "- 13 -", "Trang 12") trong dải → bỏ luôn. Dòng khác: tính khoá
    (:func:`_furniture_key`); khoá xuất hiện ở dải mép trên **≥ ``min_pages`` trang** → mọi dòng
    mang khoá đó (trong dải) bị bỏ. Trả :class:`FurnitureResult` (giữ thứ tự dòng còn lại mỗi
    trang).
    """
    # Pass 1: đếm số TRANG mỗi khoá xuất hiện ở dải mép.
    key_pages: dict[str, set[int]] = {}
    for page, lines in lines_by_page.items():
        for ln in lines:
            if not _in_band(ln.bbox, band_ratio) or is_page_number_line(ln.text):
                continue
            if _letters_len(ln.text) < min_letters:
                continue
            key = _furniture_key(ln.text, n_words)
            if key:
                key_pages.setdefault(key, set()).add(page)
    repeating = {k for k, pgs in key_pages.items() if len(pgs) >= min_pages}

    # Pass 2: bỏ (số trang trong dải) + (dòng mang khoá lặp trong dải). Giữ phần còn lại.
    kept_by_page: dict[int, list[OcrLine]] = {}
    removed = 0
    pagenum_removed = 0
    key_count: Counter[str] = Counter()
    key_text: dict[str, str] = {}
    for page, lines in lines_by_page.items():
        kept: list[OcrLine] = []
        for ln in lines:
            if _in_band(ln.bbox, band_ratio):
                if is_page_number_line(ln.text):
                    removed += 1
                    pagenum_removed += 1
                    continue
                if _letters_len(ln.text) >= min_letters:
                    key = _furniture_key(ln.text, n_words)
                    if key in repeating:
                        removed += 1
                        key_count[key] += 1
                        key_text.setdefault(key, collapse_ws(ln.text))
                        continue
            kept.append(ln)
        kept_by_page[page] = kept

    examples = [f"{key_text[k]} (×{n})" for k, n in key_count.most_common()]
    if pagenum_removed:
        examples.append(f"[số trang] (×{pagenum_removed})")
    return FurnitureResult(kept_by_page=kept_by_page, removed=removed, examples=tuple(examples))


@dataclass(frozen=True)
class HybridReport:
    """Thống kê route hybrid (đưa vào cảnh báo convert)."""

    vision_lines: int = 0
    assigned_lines: int = 0
    cross_block_lines: int = (
        0  # dòng Vision chồng ≥2 khối (nghi gộp cột) → gán theo chồng lấn lớn nhất
    )
    floating_lines: int = 0  # dòng không chồng khối nào → gom thành đoạn riêng, chèn theo vị trí
    furniture_lines: int = 0  # dòng đồ đạc (tiêu đề chạy + số trang) bỏ ở mức dòng (Việc 1)
    furniture_examples: tuple[str, ...] = ()  # đồ đạc duy nhất đã bỏ + số lần (báo cáo)
    dropped_empty_blocks: int = (
        0  # khối chữ trên trang CÓ cache mà không nhận dòng Vision nào → BỎ (không lấy lớp ABBYY)
    )
    fallback_pages: tuple[int, ...] = ()  # trang KHÔNG có cache → giữ chữ Docling/ABBYY
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _non_space_len(text: str) -> int:
    return sum(1 for ch in text if not ch.isspace())


def _norm_bbox_tl(bb, page_w: float, page_h: float) -> BBox | None:
    """BoundingBox Docling → chuẩn hoá trên-trái [x0,y0,x1,y1] ∈ [0,1]; ``None`` nếu thiếu toạ độ.

    Dùng chung cho bbox **khối** (``prov[0].bbox``) và bbox **ô bảng** (``TableCell.bbox``) — cùng
    hệ toạ độ điểm, cùng cách quy về trên-trái (``to_top_left_origin``; dự phòng lật ``y``).
    """
    if bb is None or page_w <= 0 or page_h <= 0:
        return None
    try:
        tl = bb.to_top_left_origin(page_height=page_h)
        left, top, right, bot = tl.l, tl.t, tl.r, tl.b
    except Exception:
        left, top, right, bot = bb.l, page_h - bb.t, bb.r, page_h - bb.b
    x0, x1 = sorted((left / page_w, right / page_w))
    y0, y1 = sorted((top / page_h, bot / page_h))
    return (x0, y0, x1, y1)


def _norm_bbox(item, page_w: float, page_h: float) -> BBox | None:
    """Bbox khối Docling (``prov[0].bbox``) → chuẩn hoá trên-trái [0,1]; ``None`` nếu thiếu toạ."""
    prov = getattr(item, "prov", None)
    if not prov:
        return None
    return _norm_bbox_tl(prov[0].bbox, page_w, page_h)


def _norm_table_cells(
    item, page_w: float, page_h: float
) -> tuple[tuple[tuple[BBox, int, int], ...], int, int]:
    """Ô bảng Docling (``item.data.table_cells``) → ``(cells, n_rows, n_cols)``.

    ``cells`` = các ``(bbox_chuẩn_hoá, row_idx, col_idx)`` có đủ toạ độ (bỏ ô thiếu bbox). Dùng để
    gán dòng Vision vào ô theo chồng lấn (:func:`_table_rows_from_lines`) → bảng mang chữ Vision.
    """
    data = getattr(item, "data", None)
    cells_in = getattr(data, "table_cells", None) or []
    n_rows = int(getattr(data, "num_rows", 0) or 0)
    n_cols = int(getattr(data, "num_cols", 0) or 0)
    out: list[tuple[BBox, int, int]] = []
    for c in cells_in:
        r = getattr(c, "start_row_offset_idx", None)
        col = getattr(c, "start_col_offset_idx", None)
        nb = _norm_bbox_tl(getattr(c, "bbox", None), page_w, page_h)
        if nb is None or r is None or col is None:
            continue
        out.append((nb, int(r), int(col)))
    return tuple(out), n_rows, n_cols


def _table_rows_from_lines(t: _Target) -> tuple[tuple[str, ...], ...]:
    """Dựng lưới bảng từ **dòng Vision** gán vào target: mỗi dòng → ô chồng lấn LỚN NHẤT (theo bbox
    ô); hoà không ô nào chồng thì về ô gần tâm nhất (không mất dòng — dòng đã được coi là "trong
    bảng" ở :func:`_assign_lines`). Chữ ô = nối dòng theo **thứ tự Vision** (nhất quán
    :func:`_target_text`), chuẩn hoá NFC. Trả lưới ``n_rows × n_cols`` (ô rỗng = ``""``).
    """
    if not t.table_cells or t.n_rows <= 0 or t.n_cols <= 0:
        return ()
    cell_lines: dict[tuple[int, int], list[OcrLine]] = {}
    for ln in t.lines:  # GIỮ thứ tự Vision
        best_cell: tuple[int, int] | None = None
        best_ov = 0.0
        for cbb, r, c in t.table_cells:
            ov = _overlap_frac(ln.bbox, cbb)
            if ov > best_ov:
                best_ov, best_cell = ov, (r, c)
        if best_cell is None:  # không chồng ô nào → ô gần tâm nhất (giữ dòng, không mất)
            nearest = min(t.table_cells, key=lambda cell: _center_dist2(ln.bbox, cell[0]))
            best_cell = (nearest[1], nearest[2])
        cell_lines.setdefault(best_cell, []).append(ln)
    grid = [["" for _ in range(t.n_cols)] for _ in range(t.n_rows)]
    for (r, c), lns in cell_lines.items():
        if 0 <= r < t.n_rows and 0 <= c < t.n_cols:
            grid[r][c] = normalize_text(" ".join(ln.text for ln in lns))
    return tuple(tuple(row) for row in grid)


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
    # Bảng: hình học ô (bbox chuẩn hoá + row/col) + kích thước lưới — để gán dòng Vision vào ô.
    table_cells: tuple[tuple[BBox, int, int], ...] = ()
    n_rows: int = 0
    n_cols: int = 0


def _assign_lines(
    targets: list[_Target], lines_by_page: dict[int, list[OcrLine]]
) -> tuple[int, int, dict[int, list[OcrLine]]]:
    """Gán dòng Vision vào target theo chồng lấn.

    Trả ``(assigned, cross_block, floating_by_page)`` với ``floating_by_page`` khoá theo **trang
    Docling 1-based**. Dòng **trôi** (không chồng khối nào ≥ :data:`_MIN_OVERLAP`) KHÔNG còn bị nhét
    vào khối gần nhất — làm vậy kéo chữ sang khối khác cột (SPIKE-5 v5.1) — mà trả riêng để
    :func:`_insert_floating` gom thành đoạn, chèn theo vị trí. Dòng trên trang KHÔNG có khối Docling
    nào cũng là dòng trôi (giữ lại, không mất độ phủ).
    """
    by_page: dict[int, list[_Target]] = {}
    for t in targets:
        by_page.setdefault(t.page, []).append(t)
    assigned = cross = 0
    floating_by_page: dict[int, list[OcrLine]] = {}
    cache_pages = {p + 1 for p in lines_by_page}  # cache 0-based → trang Docling 1-based
    for t_page in sorted(by_page.keys() | cache_pages):
        tgts = by_page.get(t_page, [])
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
            else:  # không chồng khối nào → dòng trôi (xử lý riêng, KHÔNG nhét vào khối gần nhất)
                floating_by_page.setdefault(t_page, []).append(line)
    return assigned, cross, floating_by_page


# Dòng trôi cách nhau theo chiều dọc (chuẩn hoá) > ngưỡng này → tách sang đoạn trôi mới.
_FLOAT_GAP = 0.03


def _group_floating(page: int, lines: list[OcrLine]) -> list[_Target]:
    """Gom dòng trôi 1 trang thành các đoạn (``_Target`` giả, label text, item ``None``).

    Sắp theo (y, x) rồi tách khi cách dọc > :data:`_FLOAT_GAP`. ``bbox`` mỗi đoạn = bao của nhóm (để
    :func:`_insert_floating` chèn theo y). Giữ thứ tự (y, x) trong đoạn — dòng trôi không thuộc cột
    nào nên đọc trên→dưới là hợp lý.
    """
    groups: list[list[OcrLine]] = []
    for ln in sorted(lines, key=lambda o: (o.bbox[1], o.bbox[0])):
        if groups and ln.bbox[1] - groups[-1][-1].bbox[1] <= _FLOAT_GAP:
            groups[-1].append(ln)
        else:
            groups.append([ln])
    out: list[_Target] = []
    for g in groups:
        bbox = (
            min(o.bbox[0] for o in g),
            min(o.bbox[1] for o in g),
            max(o.bbox[2] for o in g),
            max(o.bbox[3] for o in g),
        )
        t = _Target(-1, page, "text", bbox, 0, None)
        t.lines = g
        out.append(t)
    return out


def _insert_floating(
    order_items: list[dict], floating_by_page: dict[int, list[OcrLine]]
) -> tuple[list[dict], int]:
    """Chèn các đoạn trôi vào ``order_items`` theo vị trí, giữ thứ tự đọc Docling của khối thật.

    Mỗi trang: gom dòng trôi thành đoạn (:func:`_group_floating`), chèn mỗi đoạn **trước** khối thật
    cùng trang đầu tiên có mép trên thấp hơn đoạn (theo y). Trả ``(order_items_mới, số_dòng_trôi)``.
    """
    n_float = sum(len(v) for v in floating_by_page.values())
    groups_by_page = {p: _group_floating(p, v) for p, v in floating_by_page.items() if v}
    result: list[dict] = []
    i, n = 0, len(order_items)
    while i < n:
        page = order_items[i]["page"]
        j = i
        while j < n and order_items[j]["page"] == page:
            j += 1
        result.extend(_merge_floating_by_y(order_items[i:j], groups_by_page.pop(page, [])))
        i = j
    # Trang có dòng trôi nhưng KHÔNG có khối thật nào trong order_items → thêm cuối (giữ mọi dòng).
    for page in sorted(groups_by_page):
        result.extend(_float_entry(t) for t in groups_by_page[page])
    return result, n_float


def _float_entry(t: _Target) -> dict:
    return {"item": None, "label": "text", "page": t.page, "bbox": t.bbox, "target": t}


def _merge_floating_by_y(run: list[dict], groups: list[_Target]) -> list[dict]:
    """Chèn đoạn trôi (đã sắp theo y) vào ``run`` (khối thật 1 trang, giữ nguyên thứ tự Docling)."""
    out = list(run)
    for g in groups:  # tăng dần theo y
        gy = g.bbox[1]
        pos = len(out)
        for k, e in enumerate(out):
            ey = e["bbox"][1] if e["bbox"] else None
            if ey is not None and ey > gy:
                pos = k
                break
        out.insert(pos, _float_entry(g))
    return out


def _assemble_blocks(
    order_items: list[dict],
    doc,
    cached_pages: set[int],
    *,
    text_in_picture_min_chars: int = TEXT_IN_PICTURE_MIN_CHARS,
) -> tuple[list[Block], int]:
    """Dựng blocks theo thứ tự ``order_items``; chữ từ Vision. Trả ``(blocks, dropped)``.

    Trang **CÓ cache** (``page-1 ∈ cached_pages``): khối chữ chỉ lấy chữ Vision — khối không nhận
    dòng Vision nào → **BỎ** (đếm vào ``dropped``), KHÔNG lấy lớp chữ ABBYY; picture không có chữ
    Vision → ảnh **không caption** (không lấy caption ABBYY); **bảng** lấy chữ Vision theo ô
    (:func:`_table_rows_from_lines`) — không dòng Vision nào → **BỎ** (không lấy lưới ABBYY). Trang
    **KHÔNG cache** (fallback): giữ lớp chữ Docling/ABBYY (``item.text`` / ``_table_rows``) như v4.
    ``cached_pages`` theo **0-based** (khoá cache).
    """
    blocks: list[Block] = []
    dropped = 0
    for e in order_items:
        item, label, page, t = e["item"], e["label"], e["page"], e["target"]
        has_cache = (page - 1) in cached_pages
        if label in _HEADING_LABELS:
            text, conf = _target_text(t) if t else ("", None)
            if not text and not has_cache:
                text = normalize_text(getattr(item, "text", "") or "")
            if not text:
                dropped += 1 if (has_cache and t is not None) else 0
                continue
            blocks.append(
                Heading(text=text, level=(t.level if t else 1), page=page, confidence=conf)
            )
        elif label in _PARA_LABELS:
            text, conf = _target_text(t) if t else ("", None)
            if not text and not has_cache:
                text = normalize_text(getattr(item, "text", "") or "")
            if not text:
                dropped += 1 if (has_cache and t is not None) else 0
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
                # Trang có cache: caption chỉ từ chữ Vision (có thể rỗng); KHÔNG lấy caption ABBYY.
                caption = text if has_cache else (text or _caption_text(item, doc))
                blocks.append(ImageBlock(png=png, page=page, caption=caption))
        elif label == "table":
            if has_cache:
                # Trang CÓ cache: ô bảng lấy chữ Vision (gán theo bbox ô); không có dòng Vision nào
                # → BỎ bảng (KHÔNG lấy lưới ABBYY) — bất biến A mở sang ô bảng (Việc 1).
                rows = _table_rows_from_lines(t) if t is not None else ()
                if any(cell for row in rows for cell in row):
                    blocks.append(Table(rows=rows, page=page))
                else:
                    dropped += 1 if t is not None else 0
            else:
                from .docling_adapter import _table_rows

                rows = _table_rows(item)  # fallback: giữ lưới ABBYY như v4
                if rows:
                    blocks.append(Table(rows=rows, page=page))
        elif label == "caption":
            text, _conf = _target_text(t) if t else ("", None)
            if not text and not has_cache:
                text = normalize_text(getattr(item, "text", "") or "")
            if not text:
                dropped += 1 if (has_cache and t is not None) else 0
                continue
            if blocks and isinstance(blocks[-1], ImageBlock) and not blocks[-1].caption:
                prev = blocks[-1]
                blocks[-1] = ImageBlock(png=prev.png, page=prev.page, caption=text)
            else:
                blocks.append(Paragraph(text=text, page=page))
    return blocks, dropped


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


def _build_targets(doc) -> tuple[list[dict], list[_Target]]:
    """Thu khối Docling theo thứ tự đọc → ``(order_items, targets)``.

    Khối chữ/caption/picture có bbox → một :class:`_Target` nhận chữ Vision. Tách riêng để
    ``extract_blocks_hybrid`` và script đo (SPIKE-5) dùng chung **một** lần convert Docling.
    """
    page_size: dict[int, tuple[float, float]] = {}
    for pno, page in getattr(doc, "pages", {}).items():
        size = getattr(page, "size", None)
        if size is not None:
            page_size[pno] = (float(size.width), float(size.height))

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
        elif label == "table" and bbox is not None:
            # Bảng cũng là target → dòng Vision vùng bảng được GÁN vào bảng (không "trôi" thành
            # đoạn nhân đôi), rồi phân vào ô theo bbox ô (Việc 1 — bất biến A mở sang ô bảng).
            cells, n_rows, n_cols = _norm_table_cells(item, w, h)
            t = _Target(len(targets), page, "table", bbox, 0, item)
            t.table_cells = cells
            t.n_rows = n_rows
            t.n_cols = n_cols
            targets.append(t)
            entry["target"] = t
        order_items.append(entry)
    return order_items, targets


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

    # 1) Thu các khối theo thứ tự đọc; khối chữ/picture có bbox → target nhận chữ Vision.
    order_items, targets = _build_targets(doc)

    # 2) Bỏ ĐỒ ĐẠC (tiêu đề chạy + số trang) ngay ở mức dòng Vision, TRƯỚC khi gán vào khối — nên
    #    không lọt vào thân bài cũng không tạo đoạn trôi (Việc 1). ``total_lines`` giữ theo cache
    #    gốc
    #    để bất biến B = assigned + floating + furniture = tổng dòng cache.
    orig_lines_by_page = {p.page: list(p.lines) for p in cache.pages}
    total_lines = sum(len(v) for v in orig_lines_by_page.values())
    furniture = detect_furniture(orig_lines_by_page)
    lines_by_page = furniture.kept_by_page

    # 3) Gán dòng Vision (đã bỏ đồ đạc) vào target; dòng trôi để riêng (không nhét khối gần nhất).
    assigned, cross, floating_by_page = _assign_lines(targets, lines_by_page)
    cached_pages = set(lines_by_page)  # 0-based
    # 4) Gom dòng trôi thành đoạn riêng, chèn vào thứ tự đọc theo vị trí (y).
    order_items, floating = _insert_floating(order_items, floating_by_page)
    fallback_pages = tuple(
        sorted({e["page"] - 1 for e in order_items if (e["page"] - 1) not in cached_pages})
    )

    # 5) Dựng blocks: trang có cache chỉ dùng chữ Vision (khối rỗng → bỏ); thiếu cache → fallback.
    blocks, dropped = _assemble_blocks(
        order_items, doc, cached_pages, text_in_picture_min_chars=text_in_picture_min_chars
    )

    warnings: list[str] = []
    if furniture.removed:
        warnings.append(
            f"{furniture.removed} dòng đồ đạc (tiêu đề chạy + số trang) bỏ ở mức dòng Vision: "
            f"{list(furniture.examples[:8])}{'…' if len(furniture.examples) > 8 else ''}"
        )
    if cross:
        warnings.append(
            f"{cross} dòng Vision chồng ≥2 khối (nghi gộp cột) — gán theo chồng lấn lớn nhất"
        )
    if dropped:
        warnings.append(
            f"{dropped} khối chữ trên trang CÓ cache không nhận dòng Vision nào → bỏ "
            "(không lấy lớp chữ ABBYY)"
        )
    if floating:
        pct = 100.0 * floating / total_lines if total_lines else 0.0
        over = " — CẢNH BÁO >5%: soát ngưỡng chồng lấn / hệ toạ độ bbox" if pct > 5.0 else ""
        warnings.append(
            f"{floating} dòng Vision trôi (không chồng khối Docling nào ≥{_MIN_OVERLAP:.0%}) "
            f"= {pct:.1f}% → gom thành đoạn riêng, chèn theo vị trí{over}"
        )
    if fallback_pages:
        warnings.append(
            f"{len(fallback_pages)} trang không có cache OCR → giữ chữ Docling (ABBYY): "
            f"{list(fallback_pages[:10])}{'…' if len(fallback_pages) > 10 else ''}"
        )
    report = HybridReport(
        vision_lines=total_lines,
        assigned_lines=assigned,
        cross_block_lines=cross,
        floating_lines=floating,
        furniture_lines=furniture.removed,
        furniture_examples=furniture.examples,
        dropped_empty_blocks=dropped,
        fallback_pages=fallback_pages,
        warnings=tuple(warnings),
    )
    return blocks, report
