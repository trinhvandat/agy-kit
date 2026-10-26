# sepia-pipeline

Pipeline **PDF → EPUB sạch** cho [Sepia](../README.md), chạy bằng **Python trên máy tính**
(không chạy trên điện thoại). Đây là phần tách rời khỏi app KMP.

> Hai lệnh:
> - **`detect`** (Mốc 0) — phân loại PDF theo trang/span (Unicode / font cũ TCVN3–VNI / scan / trắng).
> - **`convert`** (Mốc 1) — PDF → EPUB sạch (trích theo span → chuyển mã legacy → reflow bỏ
>   header/footer + ghép đoạn → heading/TOC → dựng EPUB tất định → kiểm chất lượng nhẹ + epubcheck).
>
> Xem [docs/07-roadmap.md](../docs/07-roadmap.md), [docs/03-pdf-pipeline.md](../docs/03-pdf-pipeline.md).

## License & ranh giới AGPL (QUAN TRỌNG)

PyMuPDF **và** ebooklib là **AGPL-3.0**. Pipeline này chạy **tách rời** app, chỉ xuất
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
uv sync                 # tạo .venv và cài PyMuPDF + ebooklib + dev deps (pytest, ruff, epubcheck)
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

## Chạy lệnh `convert` (PDF → EPUB)

```bash
# Ra pdf-pipeline/out/<tên>.epub, CSS mặc định font-family: serif
uv run python -m sepia_pipeline convert "samples/Sách.pdf"

# Chỉ định file ra + font profile để đọc thử bằng app ngoài (KOReader…)
uv run python -m sepia_pipeline convert "samples/Sách.pdf" -o out/sach.epub --font-profile dongy

uv run python -m sepia_pipeline convert "samples/Sách.pdf" --no-check   # bỏ qua epubcheck (nhanh hơn)
uv run python -m sepia_pipeline convert "samples/Sách.pdf" --json       # báo cáo JSON
```

Báo cáo in: đường dẫn EPUB, **`bookUid`** (= `sepia:` + SHA-256 PDF gốc, ổn định giữa các lần
build — docs/04 §6), số trang/trang ảnh, số chương/ảnh nhúng, đoạn/heading, **tỷ lệ ký tự rác**,
kết quả **epubcheck**, và **cảnh báo** (nhiều cột, đoạn ngắn bất thường…).

### Cờ

| Cờ | Ý nghĩa |
|----|---------|
| `-o, --output` | File `.epub` ra (mặc định `pdf-pipeline/out/<tên>.epub`) |
| `--font-profile <tên>` | Ghi `font-family` cụ thể vào CSS, đọc từ [`font_profiles.toml`](./font_profiles.toml) (vd `dongy`, `serif`). **Không nhúng file font.** Bỏ cờ → CSS chỉ `serif` (app Sepia tự quyết font) |
| `--no-check` | Bỏ qua epubcheck |
| `--json` | In báo cáo JSON |

### Điều đã làm / bỏ qua & giới hạn đã biết (Mốc 1)

- **Trích theo span** (`get_text("dict", sort=True)`), giữ bbox/font/cỡ/đậm-nghiêng; chuyển mã
  **TCVN3** theo từng span (sau khi trích). **VNI chưa có bảng** (chưa có sách VNI mẫu để xác thực
  — SPIKE-3) → span VNI/other **giữ nguyên + cảnh báo**, không đoán bừa.
- **Bỏ header/footer/số trang**: dòng trong dải mép lặp ≥ 30% số trang (bỏ chữ số khi so khớp) +
  dòng dạng số trang. **Ghép đoạn** nối dòng tới khi gặp dấu kết câu / thụt dòng / cách dòng bất
  thường; **đoạn vắt qua trang vẫn nối**. **KHÔNG** de-hyphenation (tiếng Việt viết rời âm tiết).
- **Heading → TOC**: theo cỡ chữ (lớn hơn thân bài) + độ đậm; loại dòng mục lục (chấm dẫn), số
  trang trần, mảnh rác nhiều ký hiệu. Chia **chương theo heading cấp 1**.
- **Trang ảnh** (US-A6): trang ảnh phủ kín + rất ít chữ → render nguyên trang PNG (150 dpi) chèn
  vào dòng chảy. Ảnh nhỏ trong trang chữ: **bỏ qua** giai đoạn này.
- **EPUB tất định**: cùng PDF + cùng `PIPELINE_VERSION` → EPUB **giống hệt từng byte** (cố định
  `dcterms:modified`, ngày trong zip, thứ tự file, tên ảnh, mức nén).
- **Giới hạn**: (1) **nhiều cột / sidebar** chỉ *phát hiện + cảnh báo*, thứ tự đọc có thể lẫn;
  (2) phân **cấp heading** còn thô với sách có quá nhiều cỡ chữ → đôi khi ít chương cấp 1; (3) lỗi
  **chất lượng text nguồn** (một số trang PDF thiếu chữ ở mép, glyph trang trí) không sửa được ở
  pipeline; (4) ngưỡng trong `ReflowConfig`/`TocConfig` còn hiệu chỉnh tiếp sau khi đọc KOReader
  (SPIKE-4).

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
├── font_profiles.toml       # hồ sơ font cho --font-profile (dongy, serif…)
├── out/                      # EPUB sinh ra (gitignore)
├── sepia_pipeline/
│   ├── __init__.py          # PIPELINE_VERSION
│   ├── __main__.py          # CLI mỏng (argparse) — detect + convert
│   ├── detect.py            # phân loại trang/span
│   ├── model.py             # mô hình trung gian bất biến (TextSpan/Line/Page/Document/Block)
│   ├── extract.py           # trích theo span (PyMuPDF) → model
│   ├── legacy_encoding.py   # TCVN3 → Unicode theo span (bảng libiconv)
│   ├── reflow.py            # bỏ header/footer, ghép đoạn, trang ảnh, phát hiện nhiều cột
│   ├── toc.py               # nhận diện heading theo cỡ chữ → cấp TOC
│   ├── build_epub.py        # dựng EPUB tất định (ebooklib) + font profile
│   ├── quality.py           # kiểm chất lượng nhẹ + epubcheck
│   └── convert.py           # điều phối extract→reflow→build→quality
└── tests/                   # fixtures PDF sinh bằng code; test từng module + tích hợp convert
```

Thiết kế để **dễ bọc thành service** sau này: mỗi bước là **hàm thuần** trên mô hình bất biến
(test được không cần PyMuPDF); các adapter PyMuPDF là lớp mỏng; CLI mỏng; **không dùng cấu hình
toàn cục** (mọi ngưỡng đi qua `DetectConfig` / `ReflowConfig` / `TocConfig` / `QualityConfig`).
