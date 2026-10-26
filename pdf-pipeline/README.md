# sepia-pipeline

Pipeline **PDF → EPUB sạch** cho [Sepia](../README.md), chạy bằng **Python trên máy tính**
(không chạy trên điện thoại). Đây là phần tách rời khỏi app KMP.

> **Mốc 0** (hiện tại): chỉ có bước **`detect`** — phân loại PDF theo trang và theo span
> (có chữ Unicode / font cũ TCVN3–VNI / scan / trắng). Các bước
> `extract` / `legacy_encoding` / `reflow` / `toc` / `build_epub` / `quality` thuộc **Mốc 1**
> (xem [docs/07-roadmap.md](../docs/07-roadmap.md), [docs/03-pdf-pipeline.md](../docs/03-pdf-pipeline.md)).

## License & ranh giới AGPL (QUAN TRỌNG)

PyMuPDF (và sau này ebooklib) là **AGPL-3.0**. Pipeline này chạy **tách rời** app, chỉ xuất
`.epub`/báo cáo ra file; **app KMP không link** mã AGPL. Giữ ranh giới này để sau có thể thương
mại hóa biến thể mà không vướng AGPL (xem [ADR-004](../docs/05-tech-decisions.md),
[R-08](../docs/06-risks.md)).

## Yêu cầu

- Python **≥ 3.11**
- [`uv`](https://docs.astral.sh/uv/) (khuyến nghị). Không có uv → dùng `venv` + `pip` (bên dưới).

## Cài đặt

### Dùng uv (khuyến nghị)

```bash
cd pdf-pipeline
uv sync                 # tạo .venv và cài PyMuPDF + dev deps (pytest, ruff)
```

### Không có uv — venv + pip

```bash
cd pdf-pipeline
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e . --group dev   # pip ≥ 25.1 (đọc [dependency-groups] trong pyproject)
# pip cũ hơn → cài dev deps riêng:
#   pip install -e . && pip install pytest ruff
```

> PyMuPDF ghim trong dải **1.27.x** (bản mới nhất 1.27.x = `1.27.2.3`, kiểm 2026-10) để khớp
> tài liệu thiết kế. 2.0 đã có nhưng nâng là quyết định riêng.

## Chạy lệnh `detect`

```bash
# Một hoặc nhiều PDF; in báo cáo cho từng file
uv run python -m sepia_pipeline detect sach1.pdf sach2.pdf

# Dạng JSON (để script khác đọc)
uv run python -m sepia_pipeline detect --json sach1.pdf
```

`detect` **không** quét thư mục và **không** làm báo cáo tổng hợp — truyền thẳng danh sách file.

Mỗi file in: **loại chính**, **phân bố nhãn theo trang**, **tên font legacy** gặp được, số trang
**scan/empty**. PDF lỗi/có mật khẩu → in dòng `error` kèm lý do, không crash.

### Nhãn phân loại

| Nhãn | Ý nghĩa |
|------|---------|
| `text_unicode` | Trang có chữ, mã Unicode bình thường |
| `legacy_tcvn3` | Span dùng font cũ TCVN3/ABC (`.VnTime`…) hoặc heuristic nghi TCVN3 |
| `legacy_vni` | Span dùng font cũ VNI (`VNI-Times`…) |
| `legacy_other` | Nghi font cũ (heuristic) nhưng không rõ TCVN3 hay VNI |
| `scan` | Ít chữ + có ảnh phủ phần lớn trang (ảnh scan, chưa có text) |
| `scan_ocr` | Đủ chữ + ảnh phủ phần lớn trang **và** phần lớn chữ là **ẩn** (render mode 3) → ảnh scan + lớp OCR |
| `empty` | Ít chữ, không có ảnh lớn (trang trắng/gần trắng) |
| `mixed` | Một trang trộn nhiều loại mã (vd vừa Unicode vừa legacy) |

> **`scan_ocr` cần bằng chứng chữ ẩn.** Chỉ "ảnh phủ kín + đủ chữ" là **chưa đủ**: nếu chữ
> **hiển thị thật** (vd chữ in trên nền ảnh) thì trang được phân loại theo mã chữ bình thường
> (`text_unicode`/`legacy_*`…) và chỉ bật cờ `has_full_page_image = true`. Để thành `scan_ocr`
> cần `hidden_text_ratio ≥ scan_ocr_hidden_min` (mặc định 0.5).
>
> Các trường bổ trợ trong `PageResult` (JSON): `hidden_text_ratio` (tỷ lệ ký tự vẽ ẩn — chỉ đo
> khi có ảnh phủ kín, trang khác = 0.0), `has_full_page_image` (có ảnh phủ ≥ ngưỡng, dù nhãn là
> gì), `coverage_is_lower_bound` (độ phủ đã **dừng sớm** nên chỉ là **cận dưới** — xảy ra ở trang
> rất nhiều ảnh).

### Ngưỡng (có thể chỉnh — `DetectConfig`)

Xem docstring trong [`sepia_pipeline/detect.py`](./sepia_pipeline/detect.py). Mặc định:

- `scan_min_chars = 30` — dưới mức này (không tính khoảng trắng) trang bị coi là ít chữ.
- `scan_image_coverage = 0.70` — ít chữ **và** ảnh phủ (union) ≥ 70% diện tích → `scan`
  (tính hợp các ảnh để bắt cả scan bị cắt thành nhiều dải).
- `legacy_char_ratio_threshold = 0.15` — tỷ lệ ký tự "nghi legacy" vượt mức này → gắn cờ legacy
  dù tên font sạch (bắt font bị đổi tên). **Heuristic để gắn cờ nghi ngờ, không tuyệt đối.**
- `legacy_min_chars = 6` — span quá ngắn (dưới bấy nhiêu ký tự chữ/nghi) thì bỏ qua heuristic,
  tránh dương tính giả ở mẩu toàn ký hiệu (vd « » °).
- `mixed_min_fraction = 0.15` — nếu ≥ 2 loại mã mỗi loại chiếm ≥ 15% chữ của trang → `mixed`.

> **Giới hạn heuristic ký tự (recall thấp — cần hiệu chỉnh ở SPIKE-0):** chỉ tính là "rác" các
> ký tự Latin-1 **không** thuộc tập nguyên âm tiếng Việt hợp lệ (vùng `0x80–0xBF` + các chữ
> `0xC0–0xFF` kiểu Ä Æ Ö Þ ä æ ÷ …). Vì nguyên âm Việt precomposed (à é ô õ…) **dùng chung**
> vùng `0xC0–0xFF`, không thể mở rộng thêm mà không bắt nhầm chữ Việt sạch → một số mis-decode
> "nhẹ" vẫn có thể lọt. Chạy `detect` trên sách thật rồi **chỉnh `legacy_char_ratio_threshold`**;
> nhãn cuốn luôn kèm phân bố theo trang để kiểm tra bằng mắt.

## Test & lint

```bash
uv run pytest        # test (fixtures PDF sinh bằng code, không cần sách thật)
uv run ruff check    # lint
```

## Cấu trúc

```
pdf-pipeline/
├── pyproject.toml
├── README.md
├── sepia_pipeline/
│   ├── __init__.py          # PIPELINE_VERSION
│   ├── __main__.py          # CLI mỏng (argparse) — python -m sepia_pipeline
│   └── detect.py            # logic phân loại (hàm thuần + adapter PyMuPDF)
└── tests/
    ├── conftest.py          # fixtures PDF sinh bằng PyMuPDF
    ├── test_detect_fonts.py
    ├── test_detect_heuristic.py
    ├── test_detect_page.py
    └── test_detect_pdf.py
```

Thiết kế để **dễ bọc thành service** sau này: mỗi bước là **hàm thuần** (nhận đường dẫn/dữ liệu,
trả kết quả có cấu trúc — `PageResult`/`BookResult`); CLI chỉ là lớp mỏng; **không dùng cấu hình
toàn cục** (mọi ngưỡng đi qua `DetectConfig`).
