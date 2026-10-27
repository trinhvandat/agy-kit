"""SPIKE-5 (bổ sung) — CER/WER thực đo trên ground-truth tự chép tay.

Vì sao có script này: thước đo gốc của spike (tỷ lệ token KHÔNG phải âm tiết tiếng Việt
hợp lệ) **bỏ sót** mọi lỗi OCR mà kết quả **vẫn là âm tiết hợp lệ** (phổi→phối, nằm→năm,
mỏm→móm, của→cúa, dọc→doc, và→va…). Để đo đúng, dùng **ground truth** (chép tay từ ảnh
300 DPI, NFC) + **CER/WER** chuẩn, tách riêng **văn xuôi (@prose)** và **nhãn hình (@label)**.

Không gọi Vision: đọc văn bản OCR đã lưu sẵn trong ``out/spike5/pXXXX_{hidden,vision}.txt``
(hidden = lớp chữ ẩn ABBYY, vision = Apple Vision). → chạy được ở CI Ubuntu (không cần Mac).

    cd pdf-pipeline
    uv run --with rapidfuzz python spikes/spike5_cer_wer.py
    # tuỳ chọn: ... <page0> <page1> ...   (mặc định 23 101 186)

Ghép cặp GT↔OCR theo **từng khối**: dùng ``rapidfuzz.fuzz.partial_ratio_alignment`` tìm
đoạn con khớp nhất của khối GT trong văn bản OCR (bất kể thứ tự đọc khác nhau giữa 2 engine),
rồi tính Levenshtein ký tự (CER) và từ (WER) trên đoạn khớp đó. Tổng hợp theo trọng số ký tự/từ.

Xuất: bảng ra stdout + ``out/spike5/cer_wer.json`` (gồm danh sách lỗi của mỗi engine, có cờ
``valid_syllable`` = lỗi mà thước đo âm tiết gốc BỎ SÓT).
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

from rapidfuzz.distance import Levenshtein
from rapidfuzz.fuzz import partial_ratio_alignment

from sepia_pipeline.vietnamese import is_vietnamese_syllable

HERE = Path(__file__).resolve().parent
GT_DIR = HERE / "gt"
# Văn bản OCR đã lưu = "cache" của bước OCR (hidden=ABBYY, vision=Apple Vision). Ưu tiên
# fixtures ĐÃ COMMIT (CI Ubuntu không có Vision/Mac vẫn chạy được); fallback out/spike5 khi
# chạy thủ công sau spike5_reocr_vision.py.
FIX_DIR = HERE / "fixtures"
OUT = HERE.parent / "out" / "spike5"
ENGINES = ("hidden", "vision")
ENGINE_LABEL = {"hidden": "ABBYY (lớp ẩn)", "vision": "Apple Vision"}
DEFAULT_PAGES = (23, 101, 186)

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def norm(s: str) -> str:
    """NFC + chuẩn hoá nháy/gạch/khoảng trắng để CER tập trung vào chữ+dấu, bỏ nhiễu ký tự lạ."""
    s = unicodedata.normalize("NFC", s)
    for a, b in (
        ("“", '"'),
        ("”", '"'),
        ("‘", "'"),
        ("’", "'"),
        ("–", "-"),
        ("—", "-"),
        ("…", "..."),
        (" ", " "),
    ):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def parse_gt(path: Path) -> list[dict]:
    """File GT: dòng '@prose'/'@label' mở một khối; các dòng sau (tới khối kế) là nội dung."""
    blocks: list[dict] = []
    kind, buf = None, []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip("\n")
        if line.startswith("#"):
            continue
        if line.strip() in ("@prose", "@label"):
            if kind and buf:
                blocks.append({"kind": kind, "text": norm(" ".join(buf))})
            kind, buf = line.strip()[1:], []
        elif line.strip():
            buf.append(line.strip())
    if kind and buf:
        blocks.append({"kind": kind, "text": norm(" ".join(buf))})
    return [b for b in blocks if b["text"]]


def match_window(gt_text: str, ocr_norm: str) -> str:
    """Đoạn con của ocr_norm khớp nhất với gt_text (căn theo biên từ)."""
    al = partial_ratio_alignment(gt_text, ocr_norm)
    if al is None:
        return ""
    lo, hi = al.dest_start, al.dest_end
    while lo > 0 and not ocr_norm[lo - 1].isspace():  # mở rộng về biên từ
        lo -= 1
    while hi < len(ocr_norm) and not ocr_norm[hi].isspace():
        hi += 1
    return ocr_norm[lo:hi].strip()


def word_ops(gt_words: list[str], hyp_words: list[str]) -> list[dict]:
    """Lỗi cấp TỪ của giả thuyết so với GT (replace/delete/insert)."""
    errs = []
    for op, i1, i2, j1, j2 in Levenshtein.opcodes(gt_words, hyp_words).as_list():
        if op == "equal":
            continue
        ref = " ".join(gt_words[i1:i2])
        hyp = " ".join(hyp_words[j1:j2])
        errs.append({"op": op, "ref": ref, "hyp": hyp})
    return errs


def main() -> int:
    pages = [int(a) for a in sys.argv[1:]] or list(DEFAULT_PAGES)
    # agg[engine][kind] = [edit_chars, gt_chars, word_edits, gt_words]
    agg: dict = {e: {k: [0, 0, 0, 0] for k in ("prose", "label", "all")} for e in ENGINES}
    errors: dict = {e: [] for e in ENGINES}
    per_page: list = []

    for pg in pages:
        gt_path = GT_DIR / f"p{pg:04d}.txt"
        blocks = parse_gt(gt_path)
        ocr = {}
        for e in ENGINES:
            name = f"p{pg:04d}_{e}.txt"
            src = FIX_DIR / name if (FIX_DIR / name).exists() else OUT / name
            ocr[e] = norm(src.read_text(encoding="utf-8"))
        page_row: dict = {"page": pg, "blocks": len(blocks), "engines": {}}
        for e in ENGINES:
            p = {k: [0, 0, 0, 0] for k in ("prose", "label", "all")}
            for b in blocks:
                gt_t, kind = b["text"], b["kind"]
                gt_w = gt_t.split()
                hyp_t = match_window(gt_t, ocr[e])
                hyp_w = hyp_t.split()
                dc = Levenshtein.distance(gt_t, hyp_t)
                dw = Levenshtein.distance(gt_w, hyp_w)
                for tgt in (kind, "all"):
                    for store in (p[tgt], agg[e][tgt]):
                        store[0] += dc
                        store[1] += len(gt_t)
                        store[2] += dw
                        store[3] += len(gt_w)
                for er in word_ops(gt_w, hyp_w):
                    er2 = {**er, "page": pg, "kind": kind}
                    # lỗi mà thước đo âm tiết gốc BỎ SÓT: hyp vẫn là 1 âm tiết Việt hợp lệ
                    hw = _WORD.findall(er["hyp"])
                    er2["valid_syllable"] = (
                        er["op"] == "replace" and len(hw) == 1 and is_vietnamese_syllable(hw[0])
                    )
                    errors[e].append(er2)
            page_row["engines"][e] = {
                k: {
                    "cer_pct": round(p[k][0] / p[k][1] * 100, 2) if p[k][1] else None,
                    "wer_pct": round(p[k][2] / p[k][3] * 100, 2) if p[k][3] else None,
                    "gt_chars": p[k][1],
                    "gt_words": p[k][3],
                }
                for k in ("prose", "label", "all")
            }
        per_page.append(page_row)

    def pct(cell):
        ec, gc, ew, gw = cell
        return (round(ec / gc * 100, 2) if gc else None, round(ew / gw * 100, 2) if gw else None)

    summary = {"pages": pages, "overall": {}, "per_page": per_page, "errors": errors}
    for e in ENGINES:
        summary["overall"][e] = {}
        for k in ("prose", "label", "all"):
            cer, wer = pct(agg[e][k])
            summary["overall"][e][k] = {
                "cer_pct": cer,
                "wer_pct": wer,
                "gt_chars": agg[e][k][1],
                "gt_words": agg[e][k][3],
            }
    report = json.dumps(summary, ensure_ascii=False, indent=2)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cer_wer.json").write_text(report, "utf-8")
    (FIX_DIR / "cer_wer.json").write_text(report, "utf-8")  # cập nhật snapshot đã commit

    # ---- in bảng ----
    print(f"Trang: {pages}  (GT tự chép tay, NFC; khớp khối bằng partial_ratio_alignment)\n")
    cols = f"{'CER prose':>10} {'WER prose':>10} | {'CER label':>10} {'WER label':>10}"
    hdr = f"{'':22} | {cols} | {'CER all':>9} {'WER all':>9}"
    print(hdr)
    print("-" * len(hdr))
    for e in ENGINES:
        o = summary["overall"][e]
        cell = {
            k: {m: ("—" if o[k][m] is None else f"{o[k][m]:.2f}%") for m in ("cer_pct", "wer_pct")}
            for k in ("prose", "label", "all")
        }
        left = f"{cell['prose']['cer_pct']:>10} {cell['prose']['wer_pct']:>10}"
        mid = f"{cell['label']['cer_pct']:>10} {cell['label']['wer_pct']:>10}"
        right = f"{cell['all']['cer_pct']:>9} {cell['all']['wer_pct']:>9}"
        print(f"{ENGINE_LABEL[e]:22} | {left} | {mid} | {right}")
    gc = summary["overall"]["hidden"]["all"]["gt_chars"]
    gw = summary["overall"]["hidden"]["all"]["gt_words"]
    print(
        f"\nGT: {gc} ký tự, {gw} từ. "
        f"prose={summary['overall']['hidden']['prose']['gt_words']} từ, "
        f"label={summary['overall']['hidden']['label']['gt_words']} từ."
    )
    for e in ENGINES:
        subs = [x for x in errors[e] if x["op"] == "replace"]
        miss = [x for x in subs if x["valid_syllable"]]
        print(
            f"\n{ENGINE_LABEL[e]}: {len(errors[e])} lỗi từ "
            f"({len(subs)} thay, {len([x for x in errors[e] if x['op'] == 'delete'])} xoá, "
            f"{len([x for x in errors[e] if x['op'] == 'insert'])} chèn). "
            f"Lỗi 'thay' mà kết quả VẪN là âm tiết hợp lệ (thước đo gốc BỎ SÓT): {len(miss)}."
        )
    print("\n→ out/spike5/cer_wer.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
