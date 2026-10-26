"""Bước 2b — Nhận diện tiêu đề theo cỡ chữ/độ đậm → cấp heading (cho TOC).

Hàm thuần trên :class:`model.Line`. Ý tưởng (docs/03 §7):

- **Cỡ thân bài** = cỡ chữ phổ biến nhất (theo **số ký tự**) trên toàn tài liệu.
- Dòng **ngắn** + cỡ chữ **lớn hơn đáng kể** thân bài (hoặc đậm + lớn hơn chút) → tiêu đề.
- Các cỡ tiêu đề phân biệt (làm tròn) được sắp giảm dần → ánh xạ sang cấp 1..``max_levels``.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .model import Line

# Dòng mục lục có dãy dấu chấm dẫn ("......"), KHÔNG phải tiêu đề.
_TOC_LEADER_RE = re.compile(r"\.{4,}|…{2,}")


@dataclass(frozen=True)
class TocConfig:
    """Ngưỡng nhận diện tiêu đề.

    - ``heading_size_factor``: cỡ ≥ ``body * factor`` mới xét là tiêu đề.
    - ``bold_heading_size_factor``: nếu **đậm** thì chỉ cần ≥ ``body * factor`` nhỏ hơn.
    - ``heading_max_chars``: tiêu đề phải ngắn (dài hơn → coi là thân bài dù cỡ lớn).
    - ``max_levels``: số cấp heading tối đa (các cỡ nhỏ hơn dồn vào cấp cuối).
    - ``size_round``: làm tròn cỡ chữ về bội số này khi gom cấp (tránh lệch 0.1pt).
    - ``min_letters`` + ``min_letter_ratio``: tiêu đề phải có đủ chữ cái và phần lớn là chữ (loại
      số trang trần "66", mảnh rác "@ iu iđ n { Ị 1", dòng ký hiệu).
    """

    heading_size_factor: float = 1.18
    bold_heading_size_factor: float = 1.06
    heading_max_chars: int = 120
    max_levels: int = 3
    size_round: float = 0.5
    min_letters: int = 2
    min_letter_ratio: float = 0.6


def _round_size(size: float, step: float) -> float:
    return round(size / step) * step


def body_size(lines: list[Line], config: TocConfig | None = None) -> float:
    """Cỡ thân bài = cỡ chữ có **tổng số ký tự** lớn nhất (làm tròn theo ``size_round``)."""
    config = config or TocConfig()
    weight: Counter[float] = Counter()
    for ln in lines:
        c = ln.char_count
        if c:
            weight[_round_size(ln.dominant_size, config.size_round)] += c
    if not weight:
        return 0.0
    return weight.most_common(1)[0][0]


def is_heading_candidate(line: Line, body: float, config: TocConfig | None = None) -> bool:
    """Dòng có phải ứng viên tiêu đề không (ngắn + lớn hơn thân bài, hoặc đậm + lớn hơn chút)."""
    config = config or TocConfig()
    c = line.char_count
    if c == 0 or c > config.heading_max_chars:
        return False
    text = line.text
    letters = sum(1 for ch in text if ch.isalpha())
    # Loại dòng mục lục (chấm dẫn), số trang trần, mảnh rác nhiều ký hiệu.
    if letters < config.min_letters or letters / c < config.min_letter_ratio:
        return False
    if _TOC_LEADER_RE.search(text):
        return False
    size = line.dominant_size
    if body <= 0:
        return False
    if size >= body * config.heading_size_factor:
        return True
    if line.is_bold and size >= body * config.bold_heading_size_factor:
        return True
    return False


def heading_size_levels(
    lines: list[Line], body: float, config: TocConfig | None = None
) -> dict[float, int]:
    """Ánh xạ **cỡ chữ (đã làm tròn) của các ứng viên tiêu đề** → cấp 1..``max_levels``.

    Cỡ lớn nhất = cấp 1. Các cỡ vượt ``max_levels`` dồn vào cấp cuối.
    """
    config = config or TocConfig()
    sizes = {
        _round_size(ln.dominant_size, config.size_round)
        for ln in lines
        if is_heading_candidate(ln, body, config)
    }
    ordered = sorted(sizes, reverse=True)
    return {size: min(i + 1, config.max_levels) for i, size in enumerate(ordered)}


def heading_level(
    line: Line, body: float, levels: dict[float, int], config: TocConfig | None = None
) -> int | None:
    """Cấp heading của một dòng, hoặc ``None`` nếu là thân bài."""
    config = config or TocConfig()
    if not is_heading_candidate(line, body, config):
        return None
    return levels.get(_round_size(line.dominant_size, config.size_round), config.max_levels)
