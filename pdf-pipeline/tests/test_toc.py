"""Test nhận diện tiêu đề (toc.py) — hàm thuần trên Line."""

from sepia_pipeline.model import Line, TextSpan
from sepia_pipeline.toc import body_size, heading_level, heading_size_levels, is_heading_candidate


def line(text: str, size: float, *, bold: bool = False) -> Line:
    span = TextSpan(text=text, font="X", size=size, bold=bold)
    return Line(page=1, bbox=(40, 100, 300, 100 + size), spans=(span,))


def test_body_size_is_most_frequent_by_chars() -> None:
    lines = [line("một đoạn thân bài dài", 10.0) for _ in range(5)]
    lines += [line("TIÊU ĐỀ", 20.0)]
    assert body_size(lines) == 10.0


def test_heading_candidate_by_size() -> None:
    body = 10.0
    assert is_heading_candidate(line("CHƯƠNG MỘT", 20.0), body)  # 2× thân bài
    assert not is_heading_candidate(line("câu thân bài bình thường", 10.0), body)
    # Dòng lớn nhưng quá dài → không phải tiêu đề.
    assert not is_heading_candidate(line("x" * 200, 20.0), body)


def test_heading_candidate_bold_small_bump() -> None:
    body = 10.0
    # Đậm + lớn hơn chút (≥1.06×) → vẫn là tiêu đề dù chưa tới 1.18×.
    assert is_heading_candidate(line("Mục nhỏ", 11.0, bold=True), body)
    assert not is_heading_candidate(line("Mục nhỏ", 11.0, bold=False), body)


def test_heading_levels_ordered_desc() -> None:
    body = 10.0
    lines = [line("Alpha", 24.0), line("Beta", 16.0), line("Gamma", 12.0)]
    levels = heading_size_levels(lines, body)
    assert levels[24.0] == 1
    assert levels[16.0] == 2
    assert levels[12.0] == 3


def test_heading_levels_capped_at_max() -> None:
    body = 10.0
    lines = [line("Alpha", 30.0), line("Beta", 24.0), line("Gamma", 18.0), line("Delta", 13.0)]
    levels = heading_size_levels(lines, body)  # max_levels=3
    assert levels[30.0] == 1 and levels[24.0] == 2 and levels[18.0] == 3
    assert levels[13.0] == 3  # cỡ thứ 4 dồn vào cấp cuối


def test_heading_candidate_rejects_junk() -> None:
    body = 10.0
    assert not is_heading_candidate(line("66", 20.0), body)  # số trang trần (không có chữ)
    assert not is_heading_candidate(line("@ { Ị 1 #", 20.0), body)  # nhiều ký hiệu
    # Dòng mục lục có chấm dẫn → không phải heading dù cỡ lớn.
    assert not is_heading_candidate(line("Chương một .......... 12", 20.0), body)
    # Tiêu đề thật vẫn nhận.
    assert is_heading_candidate(line("CHƯƠNG MỘT", 20.0), body)


def test_heading_level_none_for_body() -> None:
    body = 10.0
    lines = [line("Alpha", 20.0), line("Beta", 14.0)]
    levels = heading_size_levels(lines, body)
    assert heading_level(line("câu thường", 10.0), body, levels) is None
    assert heading_level(line("Alpha", 20.0), body, levels) == 1
