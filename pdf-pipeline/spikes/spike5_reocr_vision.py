"""SPIKE-5 — OCR **lại từ ảnh trang** (Apple Vision) vs lớp chữ ẩn ABBYY.

Trả lời câu hỏi spike (xem docs/spikes/spike-5-reocr-vision.md):
  A (CHÍNH) — OCR lại TỪ ẢNH có cho chữ đúng hơn rõ rệt không, nhanh/chậm thế nào offline trên Mac?

Engine OCR = **Apple Vision** (native macOS, offline, KHÔNG cài gì; `vi-VT` chỉ ở mức `accurate`).
Thước đo "đúng" = **tỷ lệ token KHÔNG phải âm tiết tiếng Việt hợp lệ** (dùng chính
``sepia_pipeline.vietnamese.is_vietnamese_syllable`` — cùng bộ lọc rác của pipeline, không phải
ground-truth/CER). Lỗi dấu có hệ thống của ABBYY (phưdng, Dưđi, nhiéu…) làm token **hỏng cấu trúc
âm tiết** → đo được bằng tỷ lệ này. So trên cùng tập trang: hidden layer vs Vision.

    cd pdf-pipeline
    uv run python spikes/spike5_reocr_vision.py "../samples/Tự Học Đông Y - Bùi Huy.pdf"
    # tuỳ chọn: thêm danh sách trang 0-based, vd  ... <pdf> 23 101 160
    # tuỳ chọn env: SPIKE5_DPI=300  SPIKE5_LEVEL=accurate

Xuất ra ``pdf-pipeline/out/spike5/``: ``summary.json`` (số liệu tổng + theo trang),
``p0023_hidden.txt`` / ``p0023_vision.txt`` cho các trang chẩn đoán, và ảnh render ``pXXXX.png``.
Chỉ chạy trên **macOS** (cần ``swiftc`` + Vision). Thiếu thì in hướng dẫn và thoát.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import pymupdf as fitz

from sepia_pipeline.vietnamese import is_vietnamese_syllable

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "out" / "spike5"
SWIFT_SRC = HERE / "ocr_vision.swift"
DIAG_PAGES = (23, 101)  # p24 "phương thuốc", p102 "Dưới mỏm gai đốt" (ảnh trong out/review)

_TONE = set("̣̀́̃̉")
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)  # token chỉ-chữ-cái, bỏ số/dấu câu


def _has_diacritic(tok: str) -> bool:
    """Token có mang dấu tiếng Việt (dấu thanh hoặc ă/â/ê/ô/ơ/ư/đ) — nơi lỗi OCR dấu lộ ra."""
    decomposed = unicodedata.normalize("NFD", tok)
    if any(ch in _TONE for ch in decomposed):
        return True
    return any(ch in "ăâêôơưđĂÂÊÔƠƯĐ" for ch in tok)


def _metrics(text: str) -> dict:
    toks = _WORD.findall(text)
    dia = [t for t in toks if _has_diacritic(t)]
    bad_all = [t for t in toks if not is_vietnamese_syllable(t)]
    bad_dia = [t for t in dia if not is_vietnamese_syllable(t)]
    return {
        "tokens": len(toks),
        "diacritic_tokens": len(dia),
        "bad_all": len(bad_all),
        "bad_diacritic": len(bad_dia),
        "bad_diacritic_examples": sorted(set(bad_dia))[:15],
    }


def _ensure_ocr_bin() -> Path:
    if shutil.which("swiftc") is None:
        sys.exit("Cần `swiftc` (macOS). Spike này chỉ chạy trên Mac với Apple Vision.")
    OUT.mkdir(parents=True, exist_ok=True)
    binpath = OUT / "ocr_vision"
    if not binpath.exists() or binpath.stat().st_mtime < SWIFT_SRC.stat().st_mtime:
        subprocess.run(["swiftc", "-O", str(SWIFT_SRC), "-o", str(binpath)], check=True)
    return binpath


def main() -> int:
    pdf = Path(sys.argv[1])
    dpi = int(os.environ.get("SPIKE5_DPI", "300"))
    level = os.environ.get("SPIKE5_LEVEL", "accurate")
    binpath = _ensure_ocr_bin()

    doc = fitz.open(str(pdf))
    if len(sys.argv) > 2:
        pages = [int(a) for a in sys.argv[2:]]
    else:
        pages = sorted(set(DIAG_PAGES) | set(range(25, doc.page_count - 7, 15)))
    mat = fitz.Matrix(dpi / 72, dpi / 72)

    rows, render_t, ocr_t = [], [], []
    for pi in pages:
        page = doc[pi]
        t0 = time.time()
        img = OUT / f"p{pi:04d}.png"
        page.get_pixmap(matrix=mat).save(str(img))
        render_t.append(time.time() - t0)

        hidden = page.get_text("text")
        t0 = time.time()
        proc = subprocess.run([str(binpath), str(img), level], capture_output=True, text=True)
        ocr_t.append(time.time() - t0)
        vision = proc.stdout

        if pi in DIAG_PAGES:
            (OUT / f"p{pi:04d}_hidden.txt").write_text(hidden, encoding="utf-8")
            (OUT / f"p{pi:04d}_vision.txt").write_text(vision, encoding="utf-8")

        rows.append(
            {
                "page": pi,
                "hidden": _metrics(hidden),
                "vision": _metrics(vision),
                "ocr_seconds": round(ocr_t[-1], 3),
            }
        )
    doc.close()

    def _agg(key: str) -> dict:
        tot = sum(r[key]["tokens"] for r in rows)
        dia = sum(r[key]["diacritic_tokens"] for r in rows)
        ba = sum(r[key]["bad_all"] for r in rows)
        bd = sum(r[key]["bad_diacritic"] for r in rows)
        return {
            "tokens": tot,
            "diacritic_tokens": dia,
            "bad_all": ba,
            "bad_diacritic": bd,
            "bad_all_pct": round(ba / tot * 100, 2) if tot else 0.0,
            "bad_diacritic_pct": round(bd / dia * 100, 2) if dia else 0.0,
        }

    spp = sum(ocr_t) / len(ocr_t)
    summary = {
        "pdf": pdf.name,
        "dpi": dpi,
        "level": level,
        "engine": "apple-vision",
        "pages_sampled": len(pages),
        "render_sec_per_page": round(sum(render_t) / len(render_t), 3),
        "ocr_sec_per_page": round(spp, 3),
        "est_full_book_min": round((spp + sum(render_t) / len(render_t)) * doc_pages(pdf) / 60, 1),
        "hidden_abbyy": _agg("hidden"),
        "vision": _agg("vision"),
        "per_page": rows,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")

    h, v = summary["hidden_abbyy"], summary["vision"]
    print(f"pages={len(pages)} dpi={dpi} level={level}")
    print(
        f"render {summary['render_sec_per_page']}s/pg + Vision {summary['ocr_sec_per_page']}s/pg"
        f"  → ~{summary['est_full_book_min']} phút/cuốn"
    )
    print(f"HIDDEN (ABBYY): bad-âm-tiết ALL={h['bad_all_pct']}%  DẤU={h['bad_diacritic_pct']}%")
    print(f"VISION (ảnh)  : bad-âm-tiết ALL={v['bad_all_pct']}%  DẤU={v['bad_diacritic_pct']}%")
    print("→ out/spike5/summary.json")
    return 0


def doc_pages(pdf: Path) -> int:
    d = fitz.open(str(pdf))
    n = d.page_count
    d.close()
    return n


if __name__ == "__main__":
    raise SystemExit(main())
