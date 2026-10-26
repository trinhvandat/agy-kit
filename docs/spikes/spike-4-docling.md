# SPIKE-4 — Pipeline hiện tại (heuristic PyMuPDF) vs Docling

> Thử nghiệm, **CHƯA sửa ADR** — chỉ ghi kết quả + đề xuất. Cập nhật: 2026-10-26.
> Mẫu: `Tự Học Đông Y - Bùi Huy.pdf` (sách scan **ABBYY FineReader 11**: mỗi trang = ảnh scan +
> lớp chữ OCR **hiển thị**; `detect` gắn nhãn cuốn `scan_ocr`).

## Cách chạy

```bash
cd pdf-pipeline
uv sync --extra docling                 # optional dep, nặng (torch/transformers), MIT
uv run python spikes/spike4_docling.py "../samples/Tự Học Đông Y - Bùi Huy.pdf"
```

10 trang đại diện (0-based `[0, 10, 30, 60, 99, 149, 199, 230, 260, 289]`): bìa scan, mục lục,
trang nhiều cột/sidebar (infographic), trang có hình + heading to, vài trang thân bài, phụ bản cuối.
Kết quả ở `pdf-pipeline/out/spike4/` (`current.md`, `docling.md`, `docling_pic_*.png`, `summary.json`).

Docling chạy **dùng lớp chữ có sẵn trong PDF** (`do_ocr=False`) — lớp OCR ABBYY dùng được nên
**không cần OCR lại** (`ocr_used=false`).

## Số liệu

| | Pipeline hiện tại (PyMuPDF heuristic) | Docling 2.142.1 |
|---|---|---|
| Thời gian (10 trang, CPU) | ~tức thì (<1s) | **41s (4.1s/trang)** → ~20 phút/292 trang |
| Phụ thuộc | PyMuPDF (**AGPL**) | torch/transformers… (**MIT**) nhưng rất nặng |
| Heading nhận được (10 trang) | 9, lẫn rác (vd `# s s s`) | **~17, sạch & đúng** (tên mục thật) |
| Hình trong trang | **0** (bỏ qua ảnh nhỏ; chỉ render nguyên trang cho 4 trang scan) | **10 hình** cắt rời |
| Mục lục (dot leaders) | vỡ vụn thành nhiều đoạn ngắn | nhận dạng thành **bảng** Markdown |
| OCR lại | — | không cần (dùng lớp chữ sẵn) |

## Theo từng khía cạnh

### 1. Thứ tự đọc (nhiều cột / sidebar)
- **Hiện tại**: dùng thứ tự block của PyMuPDF (`sort=True`) → trang sidebar (infographic "ĐẶC TRƯNG
  CỦA THỂ CHẤT KHÍ HƯ") bị **trộn/cắt vụn** thành nhiều đoạn ngắn (quality báo 53% đoạn < 40 ký tự).
- **Docling**: có mô hình layout → thứ tự đọc hợp lý hơn; khối infographic sidebar được coi là **một
  hình** (`<!-- image -->`) thay vì cố tách chữ → đọc dễ hơn cho sách minh hoạ.

### 2. Hình & chú thích
- **Hiện tại**: chỉ render **nguyên trang** cho trang gần như toàn ảnh; ảnh/sơ đồ nằm trong trang
  chữ bị **bỏ** (ghi cảnh báo). Sách Đông y nhiều hình → mất nhiều nội dung.
- **Docling**: cắt được **10 hình** rời trong 10 trang (lưu PNG), đặt đúng vị trí trong dòng chảy.
  **Ưu thế rõ** cho sách minh hoạ.

### 3. Heading
- **Hiện tại**: heuristic cỡ-chữ **nhạy theo thành phần tài liệu** (cùng cuốn: 398 heading; 10 trang
  con: 9) và lọt rác trang trí. Cấp heading còn thô.
- **Docling**: heading **ổn định, đúng tên mục** ("THỂ CHẤT KHÍ Hư", "CHẾ TẠO NGẢI CỨU", "MẤT NGỦ:
  DO TÂM THẦN BẤT AN"…). **Ưu thế rõ**.

### 4. Chất lượng chữ (cả hai)
Lớp OCR ABBYY có lỗi sẵn ("trơ", "tạ n g", "nhiéu", "trắm"…). **Cả hai đều kế thừa lỗi này** — không
bên nào sửa được nếu không **OCR lại** (Tesseract/Surya `vie`). Đây là giới hạn của **nguồn**.

### 5. Font cũ TCVN3/VNI (quan trọng cho ADR-004)
- Docling **không giữ font theo span** → **không** chuyển mã TCVN3/VNI được (đúng như ADR-004 đã ghi).
- Nhưng sách **scan** thì chữ đã là Unicode do OCR → không có vấn đề font cũ. Vấn đề font cũ chỉ ở
  sách **born-digital** font ABC/VNI — nơi pipeline PyMuPDF theo-span vẫn là bắt buộc.

## Đề xuất (CHƯA sửa ADR)

**Định tuyến theo loại sách** (theo nhãn `detect`), giữ cả hai đường:

1. **`text_unicode` / `legacy_*` (born-digital)** → **giữ heuristic PyMuPDF hiện tại**: nhanh, không
   phụ thuộc nặng, **giữ font theo span để chuyển mã TCVN3/VNI** (Docling không làm được).
2. **`scan_ocr` / trang nhiều cột nặng** (như mẫu này) → **dùng Docling** (dùng lớp OCR sẵn):
   reading order + heading + cắt hình tốt hơn hẳn; chấp nhận chậm (~4s/trang CPU, chạy offline theo
   lô) và thêm optional dep nặng. Lưu ý **chất lượng chữ vẫn bị chặn bởi OCR gốc**; nếu OCR gốc kém
   thì cân nhắc **OCR lại** `vie` (US-A7) thay vì tin lớp chữ ABBYY.
3. **License**: Docling là **MIT** → nếu sau thương mại hóa, đường Docling *nhẹ gánh AGPL* hơn
   PyMuPDF/ebooklib (R-08) cho khâu trích; nhưng vẫn dựng EPUB bằng ebooklib (AGPL) → ranh giới
   "pipeline tách rời app" (ADR-004) vẫn phải giữ.

**Việc nên làm tiếp (nếu chọn hướng Docling cho scan):**
- Thêm mẫu **born-digital chữ sạch** để kiểm đường heuristic (hiện chỉ có 1 mẫu, lại là scan).
- Thử **OCR lại `vie`** (OCRmyPDF/Tesseract hoặc Surya) trên vài trang để so với lớp ABBYY sẵn.
- Nếu chốt định tuyến → cập nhật **ADR-004** (thêm nhánh Docling cho `scan_ocr`) và **docs/03 §5**.

## Kết quả cả cuốn (Mốc 1b — `convert` toàn bộ 292 trang)

Chạy `convert` toàn bộ `Tự Học Đông Y - Bùi Huy.pdf` (PIPELINE_VERSION 2, đã bỏ mục lục in sẵn):

| Chỉ số | `--engine heuristic` | `--engine docling` (auto) |
|---|---|---|
| Thời gian (CPU) | ~tức thì | **~51 giây** |
| Chương (file XHTML) | 10 | **721** ⚠️ (mỗi section-header → 1 chương) |
| Hình nhúng | 4 (chỉ render nguyên trang scan) | **351 hình cắt rời** |
| Đoạn văn | 5220 | 1535 |
| Heading | 398 (lẫn rác) | 720 (sạch hơn) |
| **% đoạn < 40 ký tự** | **53.5%** (trộn cột/vụn) | **21.9%** (tốt hơn hẳn) |
| Mục lục in sẵn bỏ | 3 dòng | 12 dòng |
| Tỷ lệ ký tự rác | 0.0007 | 0.0005 |
| NFC nhất quán | ✓ | ✓ |
| epubcheck | **HỢP LỆ** | **HỢP LỆ** |
| Kích thước EPUB | 2.5 MB | **71 MB** (351 ảnh, `images_scale=2.0`) |
| Tất định (2 lần build) | ✓ byte-identical | ✓ byte-identical |

**Nhận xét**: Docling **giảm mạnh đoạn vụn** (53.5% → 21.9%) và **giữ được 351 hình** — đúng điểm yếu
nhất của heuristic trên sách minh hoạ. Hai điểm cần tinh chỉnh (ghi nhận, chưa làm ở 1b):
1. **721 chương quá nhiều** (mỗi section-header thành một file) → TOC rất dài. Hướng chỉnh: chỉ chia
   file theo heading **cấp cao nhất** + dựa thêm size-cap, hoặc gộp heading nhỏ.
2. **EPUB 71 MB** do nhúng 351 ảnh ở `images_scale=2.0` → cân nhắc hạ scale/nén để nhẹ hơn.

## Phụ lục — số liệu máy chạy
`summary.json`: `seconds=41.07`, `seconds_per_page=4.11`, `n_pictures=10`, `ocr_used=false`
(macOS, CPU; lần đầu tải thêm model layout ~vài chục MB).
