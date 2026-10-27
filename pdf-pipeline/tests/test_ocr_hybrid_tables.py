"""Test bảng route hybrid — **ô bảng lấy chữ Vision, không rò ABBYY** (fix-hybrid-tables-reanchor).

Việc 1 (PIPELINE_VERSION 7): trên trang CÓ cache, bảng không còn giữ lớp chữ ABBYY trong ``<td>``
(bất biến A mở sang MỌI loại khối, kể cả ô bảng). Dòng Vision vùng bảng được gán vào ô theo bbox ô
(Docling ``TableCell.bbox``) → bảng mang chữ Vision; bảng không nhận dòng Vision nào → BỎ (không lấy
ABBYY). Trang KHÔNG cache (fallback) vẫn giữ lưới ABBYY (``_table_rows``) như v4.

Thuần, KHÔNG cần docling/Vision: dựng ``_Target``/item giả rồi gọi thẳng hàm thuần.
"""

from __future__ import annotations

from sepia_pipeline.model import Table
from sepia_pipeline.ocr_cache import OcrLine
from sepia_pipeline.ocr_hybrid import (
    _assemble_blocks,
    _build_targets,
    _norm_table_cells,
    _table_rows_from_lines,
    _Target,
)

# --- Giả Docling table item ---------------------------------------------------


class _FakeBB:
    """Giả BoundingBox: đã ở gốc trên-trái → ``to_top_left_origin`` trả chính nó."""

    def __init__(self, left: float, top: float, right: float, bot: float):
        self.l, self.t, self.r, self.b = left, top, right, bot

    def to_top_left_origin(self, page_height: float):
        return self


class _FakeCell:
    def __init__(self, text: str, bbox=None, row: int = 0, col: int = 0):
        self.text = text
        self.bbox = bbox
        self.start_row_offset_idx = row
        self.start_col_offset_idx = col


class _FakeData:
    def __init__(self, grid=None, table_cells=None, num_rows: int = 0, num_cols: int = 0):
        self.grid = grid
        self.table_cells = table_cells
        self.num_rows = num_rows
        self.num_cols = num_cols


class _FakeProv:
    def __init__(self, bbox, page_no: int):
        self.bbox = bbox
        self.page_no = page_no


class _FakeTableItem:
    def __init__(self, data, prov=None):
        self.data = data
        self.prov = prov or []
        self.label = "table"

    def get_image(self, doc):
        return None


def _table_target(cells, n_rows, n_cols, lines, *, abbyy: str = "") -> _Target:
    t = _Target(0, 1, "table", (0.0, 0.0, 1.0, 1.0), 0, _FakeTableItem(_FakeData(grid=[[]])))
    t.item.data.grid = [[_FakeCell(abbyy)]] if abbyy else [[]]
    t.table_cells = cells
    t.n_rows = n_rows
    t.n_cols = n_cols
    t.lines = list(lines)
    return t


# --- _table_rows_from_lines: gán dòng Vision vào ô theo bbox ------------------


def test_table_rows_from_lines_assigns_each_line_to_overlapping_cell() -> None:
    cells = (
        ((0.0, 0.0, 0.5, 0.5), 0, 0),
        ((0.5, 0.0, 1.0, 0.5), 0, 1),
        ((0.0, 0.5, 0.5, 1.0), 1, 0),
        ((0.5, 0.5, 1.0, 1.0), 1, 1),
    )
    lines = [
        OcrLine("A", (0.1, 0.1, 0.3, 0.2), 0.9),
        OcrLine("B", (0.6, 0.1, 0.8, 0.2), 0.9),
        OcrLine("C", (0.1, 0.6, 0.3, 0.7), 0.9),
        OcrLine("D", (0.6, 0.6, 0.8, 0.7), 0.9),
    ]
    t = _table_target(cells, 2, 2, lines)
    assert _table_rows_from_lines(t) == (("A", "B"), ("C", "D"))


def test_table_cell_joins_multiple_lines_keeping_vision_order() -> None:
    cells = (((0.0, 0.0, 1.0, 1.0), 0, 0),)
    lines = [
        OcrLine("dưới", (0.1, 0.6, 0.9, 0.7), 0.9),  # Vision order đi trước
        OcrLine("mỏm", (0.1, 0.1, 0.9, 0.2), 0.9),
    ]
    t = _table_target(cells, 1, 1, lines)
    # GIỮ thứ tự Vision (không sắp lại theo y) — nhất quán với _target_text.
    assert _table_rows_from_lines(t) == (("dưới mỏm",),)


def test_table_line_outside_any_cell_goes_to_nearest_no_loss() -> None:
    cells = (((0.0, 0.0, 0.4, 1.0), 0, 0), ((0.6, 0.0, 1.0, 1.0), 0, 1))
    # Dòng nằm trong khe giữa hai ô, tâm x=0.48 → gần ô trái (tâm 0.2) hơn ô phải (tâm 0.8).
    lines = [OcrLine("khe", (0.46, 0.1, 0.50, 0.2), 0.9)]
    t = _table_target(cells, 1, 2, lines)
    rows = _table_rows_from_lines(t)
    assert rows == (("khe", ""),)  # không mất dòng


# --- _assemble_blocks: trang có cache dùng Vision; không có Vision → bỏ -------


def test_assemble_cached_table_uses_vision_not_abbyy() -> None:
    cells = (((0.0, 0.0, 1.0, 0.5), 0, 0), ((0.0, 0.5, 1.0, 1.0), 1, 0))
    lines = [
        OcrLine("trên", (0.1, 0.1, 0.9, 0.2), 0.9),
        OcrLine("dưới", (0.1, 0.6, 0.9, 0.7), 0.9),
    ]
    t = _table_target(cells, 2, 1, lines, abbyy="nhiéu điéu vđi")  # ABBYY phải bị bỏ
    entry = {"item": t.item, "label": "table", "page": 1, "bbox": t.bbox, "target": t}
    blocks, dropped = _assemble_blocks([entry], doc=None, cached_pages={0})
    assert [type(b).__name__ for b in blocks] == ["Table"]
    assert blocks[0].rows == (("trên",), ("dưới",))
    assert dropped == 0


def test_assemble_cached_table_without_vision_dropped_no_abbyy() -> None:
    t = _table_target((((0.0, 0.0, 1.0, 1.0), 0, 0),), 1, 1, [], abbyy="nhiéu điéu")
    entry = {"item": t.item, "label": "table", "page": 1, "bbox": t.bbox, "target": t}
    blocks, dropped = _assemble_blocks([entry], doc=None, cached_pages={0})
    assert blocks == []  # KHÔNG xuất lưới ABBYY
    assert dropped == 1


def test_assemble_noncached_table_keeps_abbyy() -> None:
    grid = [[_FakeCell("a"), _FakeCell("b")]]
    item = _FakeTableItem(_FakeData(grid=grid))
    entry = {
        "item": item,
        "label": "table",
        "page": 2,
        "bbox": (0.0, 0.0, 1.0, 1.0),
        "target": None,
    }
    blocks, dropped = _assemble_blocks([entry], doc=None, cached_pages={0})
    assert [b.rows for b in blocks if isinstance(b, Table)] == [(("a", "b"),)]
    assert dropped == 0


# --- _norm_table_cells + _build_targets: bảng là target (dòng không trôi) -----


def test_norm_table_cells_normalizes_to_unit_top_left() -> None:
    cells = [
        _FakeCell("x", _FakeBB(0, 0, 50, 50), 0, 0),
        _FakeCell("y", _FakeBB(50, 0, 100, 50), 0, 1),
    ]
    item = _FakeTableItem(_FakeData(table_cells=cells, num_rows=1, num_cols=2))
    norm, n_rows, n_cols = _norm_table_cells(item, 100.0, 100.0)
    assert (n_rows, n_cols) == (1, 2)
    assert norm == (((0.0, 0.0, 0.5, 0.5), 0, 0), ((0.5, 0.0, 1.0, 0.5), 0, 1))


class _FakeSize:
    def __init__(self, w, h):
        self.width, self.height = w, h


class _FakePage:
    def __init__(self, w, h):
        self.size = _FakeSize(w, h)


class _FakeDoc:
    def __init__(self, items, pages):
        self._items = items
        self.pages = pages

    def iterate_items(self):
        for it in self._items:
            yield it, 0


def test_build_targets_registers_table_as_target_with_cells() -> None:
    cells = [
        _FakeCell("x", _FakeBB(0, 0, 50, 100), 0, 0),
        _FakeCell("y", _FakeBB(50, 0, 100, 100), 0, 1),
    ]
    table = _FakeTableItem(
        _FakeData(table_cells=cells, num_rows=1, num_cols=2),
        prov=[_FakeProv(_FakeBB(0, 0, 100, 100), 1)],
    )
    doc = _FakeDoc([table], {1: _FakePage(100.0, 100.0)})
    order_items, targets = _build_targets(doc)
    table_targets = [t for t in targets if t.label == "table"]
    assert len(table_targets) == 1
    assert table_targets[0].n_cols == 2
    assert len(table_targets[0].table_cells) == 2
    # order_item của bảng trỏ tới target (để dòng Vision vùng bảng được gán, không trôi).
    assert order_items[0]["target"] is table_targets[0]
