"""Cycle 1 — phân loại font theo TÊN span (regex, có xử lý tiền tố subset)."""

import pytest

from sepia_pipeline.detect import classify_font_name


@pytest.mark.parametrize(
    "name",
    [
        ".VnTime",
        ".VnTimeH",
        ".VnArial",
        ".VnArialH",
    ],
)
def test_tcvn3_names_detected(name: str) -> None:
    assert classify_font_name(name) == "legacy_tcvn3"


@pytest.mark.parametrize(
    "name",
    [
        "ABCDEF+.VnTime",
        "QWERTY+.VnArial",
    ],
)
def test_tcvn3_with_subset_prefix(name: str) -> None:
    assert classify_font_name(name) == "legacy_tcvn3"


@pytest.mark.parametrize(
    "name",
    [
        "VNI-Times",
        "VNI-Helve",
        "ABCDEF+VNI-Times",
    ],
)
def test_vni_names_detected(name: str) -> None:
    assert classify_font_name(name) == "legacy_vni"


@pytest.mark.parametrize(
    "name",
    [
        "TimesNewRomanPSMT",
        "ArialMT",
        "ABCDEF+TimesNewRomanPSMT",
        "Literata",
        "Noto Serif",
        "Times New Roman",
        "",
    ],
)
def test_clean_fonts_not_matched(name: str) -> None:
    assert classify_font_name(name) is None


def test_subset_prefix_must_be_exactly_six_uppercase() -> None:
    # "ABCDE+" (5 chữ) không phải tiền tố subset hợp lệ → không được coi là .Vn hợp lệ
    assert classify_font_name("ABCDE+.VnTime") is None


@pytest.mark.parametrize(
    "name",
    [
        ".Vn3DH",  # có chữ số
        ".VnTime New",  # có khoảng trắng
        ".VnCentury Schoolbook",
        "ABCDEF+.VnTime New",
    ],
)
def test_tcvn3_names_with_digits_and_spaces(name: str) -> None:
    assert classify_font_name(name) == "legacy_tcvn3"


@pytest.mark.parametrize(
    "name",
    [
        "VNI-Times New",
        "VNI-Thuphap2",
    ],
)
def test_vni_names_with_digits_and_spaces(name: str) -> None:
    assert classify_font_name(name) == "legacy_vni"


def test_trailing_newline_not_matched() -> None:
    # fullmatch: không để '$' khớp trước '\n' lọt ký tự thừa.
    assert classify_font_name("VNI-Times\n") is None
    assert classify_font_name(".VnTime\n") is None
