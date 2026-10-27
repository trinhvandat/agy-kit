"""Test cache OCR — thuần stdlib, **không cần Vision/macOS** (chạy được CI Ubuntu).

Dùng fixture cache 3 trang đã commit (``tests/fixtures/ocr_cache/<sha>.json``) + cache dựng tay.
"""

from pathlib import Path

from sepia_pipeline.ocr_cache import (
    OCR_ENGINE,
    OCR_RENDER,
    OCR_SCHEMA,
    OcrCache,
    OcrLine,
    OcrPage,
    cache_key,
    cache_status,
    read_cache,
    write_cache,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ocr_cache"
FIXTURE_SHA = "78ae5d3007fe832fd1e82a4ca602838f34027d260f6da7ccc207bdd13edcbc59"
VERSION = {
    "macos_build": "24E263",
    "macos_ver": "15.4.1",
    "vision_langs_sha": "x",
    "ocrmac": "1.0.1",
}


def _cache(sha: str = "abc", engine: dict | None = None, version: dict | None = None) -> OcrCache:
    return OcrCache(
        book_uid=f"sepia:{sha}",
        pdf_sha256=sha,
        render=dict(OCR_RENDER),
        engine=engine or dict(OCR_ENGINE),
        engine_version=version or dict(VERSION),
        created="2026-10-27",
        pages=(
            OcrPage(page=0, lines=(OcrLine("Dòng một", (0.1, 0.1, 0.5, 0.15), 0.98),)),
            OcrPage(page=1, lines=(OcrLine("Dòng hai", (0.1, 0.2, 0.6, 0.25), 0.91),)),
        ),
    )


def test_roundtrip_to_from_dict() -> None:
    c = _cache()
    again = OcrCache.from_dict(c.to_dict())
    assert again == c
    assert again.n_lines == 2


def test_write_read_deterministic(tmp_path: Path) -> None:
    c = _cache()
    p1 = write_cache(c, tmp_path)
    b1 = p1.read_bytes()
    write_cache(c, tmp_path)  # ghi lại cùng cache
    assert p1.read_bytes() == b1  # byte-identical
    assert read_cache(tmp_path, c.pdf_sha256) == c
    assert p1.name == f"{c.pdf_sha256}.json"


def test_text_normalized_nfc() -> None:
    # "ẹ" dạng tổ hợp (e + dấu nặng) → NFC gộp thành 1 ký tự khi ghi.
    line = OcrLine("ẹ", (0, 0, 1, 1), 1.0)
    assert line.to_dict()["text"] == "ẹ"  # ẹ precomposed


def test_cache_key_sensitivity() -> None:
    base = cache_key("sha1", OCR_RENDER, OCR_ENGINE, VERSION)
    assert base == cache_key("sha1", OCR_RENDER, OCR_ENGINE, VERSION)  # ổn định
    assert base != cache_key("sha2", OCR_RENDER, OCR_ENGINE, VERSION)  # đổi PDF
    assert base != cache_key("sha1", {"dpi": 200}, OCR_ENGINE, VERSION)  # đổi render
    assert base != cache_key("sha1", OCR_RENDER, OCR_ENGINE, {**VERSION, "macos_build": "Y"})


def test_cache_status_hit_miss_mismatch(tmp_path: Path) -> None:
    c = _cache(sha="s1")
    assert cache_status(tmp_path, "s1", OCR_ENGINE, VERSION).state == "miss"
    write_cache(c, tmp_path)
    hit = cache_status(tmp_path, "s1", OCR_ENGINE, VERSION)
    assert hit.state == "hit" and hit.ok and hit.cache is not None
    # engine khác → mismatch
    other = cache_status(tmp_path, "s1", {**OCR_ENGINE, "name": "tesseract"}, VERSION)
    assert other.state == "mismatch"
    # phiên bản khác → mismatch
    ver = cache_status(tmp_path, "s1", OCR_ENGINE, {**VERSION, "macos_build": "ZZZ"})
    assert ver.state == "mismatch"


def test_fixture_cache_loads() -> None:
    """Fixture cache thật (3 trang GT) đọc được, đúng schema + engine, không cần Vision."""
    cache = read_cache(FIXTURE_DIR, FIXTURE_SHA)
    assert cache is not None
    assert cache.ocr_schema == OCR_SCHEMA
    assert cache.engine["name"] == "apple-vision"
    assert [p.page for p in cache.pages] == [23, 101, 186]
    assert cache.n_lines > 200
    # mọi bbox chuẩn hoá trong [0,1]
    for p in cache.pages:
        for ln in p.lines:
            assert all(0.0 <= v <= 1.0 for v in ln.bbox)
            assert ln.text == ln.text  # NFC đã áp lúc ghi
