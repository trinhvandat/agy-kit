"""Cycle 5 — CLI mỏng: lệnh `detect`, định dạng người đọc & --json."""

import json
from pathlib import Path

import pytest

from sepia_pipeline.__main__ import format_human, main
from sepia_pipeline.detect import TEXT_UNICODE, BookResult, PageResult


def _sample_book() -> BookResult:
    page = PageResult(
        page_number=1,
        label=TEXT_UNICODE,
        char_count=120,
        image_coverage=0.0,
        legacy_ratio=0.0,
        legacy_fonts=(".VnTime",),
    )
    return BookResult(
        path="demo.pdf",
        label=TEXT_UNICODE,
        n_pages=1,
        page_distribution={TEXT_UNICODE: 1},
        legacy_fonts=(".VnTime",),
        scan_pages=0,
        empty_pages=0,
        pages=(page,),
    )


def test_format_human_has_key_fields() -> None:
    out = format_human(_sample_book())
    assert "demo.pdf" in out
    assert TEXT_UNICODE in out
    assert ".VnTime" in out


def test_format_human_error_shows_reason() -> None:
    res = BookResult(path="bad.pdf", label=None, n_pages=0, error="PDF có mật khẩu")
    out = format_human(res)
    assert "bad.pdf" in out
    assert "error" in out.lower()
    assert "mật khẩu" in out


def test_main_json_outputs_parseable_array(unicode_vi_pdf: Path, capsys) -> None:
    code = main(["detect", "--json", str(unicode_vi_pdf)])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert isinstance(data, list)
    assert data[0]["label"] == TEXT_UNICODE
    assert data[0]["n_pages"] == 1


def test_main_human_prints_label(scan_pdf: Path, capsys) -> None:
    code = main(["detect", str(scan_pdf)])
    assert code == 0
    assert "scan" in capsys.readouterr().out


def test_main_returns_nonzero_on_error(corrupt_pdf: Path, capsys) -> None:
    code = main(["detect", str(corrupt_pdf)])
    assert code == 1
    assert "error" in capsys.readouterr().out.lower()


def test_main_handles_multiple_files(unicode_vi_pdf: Path, scan_pdf: Path, capsys) -> None:
    code = main(["detect", str(unicode_vi_pdf), str(scan_pdf)])
    assert code == 0
    out = capsys.readouterr().out
    assert str(unicode_vi_pdf) in out
    assert str(scan_pdf) in out


def test_detect_requires_at_least_one_file() -> None:
    with pytest.raises(SystemExit):
        main(["detect"])
