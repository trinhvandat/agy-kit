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

Lớp chữ PDF (PyMuPDF) = **366 215 ký tự** (mốc so độ phủ).

| Chỉ số | `--engine heuristic` | Docling (1b đầu) | Docling (sau sửa, v2) | **Docling (v3)** |
|---|---|---|---|---|
| Thời gian trích (CPU) | ~1.4 giây | ~43 giây | ~43 giây | **~43 giây** |
| **Ký tự** (trong EPUB) | 364 192 | 275 467 | 351 337 | **350 457** |
| **Từ** | 101 419 | — | 100 081 | **99 917** |
| **% độ phủ chữ** (so lớp chữ PDF) | 99.6% | 75.2% ⚠️ | 95.9% | **95.7%** |
| **Số file XHTML** | 9 | 721 ⚠️ | 7 | **7** |
| **Kích thước EPUB** | 0.3 MB | 71 MB ⚠️ | 2.7 MB | **2.7 MB** |
| **Số ảnh nhúng** | 4 | 351 | 161 | **161** |
| Heading | 398 | 720 | 720 | **703** |
| **Khối rác bỏ** (lọc âm tiết Việt) | — | — | — | **27** |
| **Header chạy đầu trang bỏ** | — | — | — | **10** |
| **% đoạn < 40 ký tự** | 53.5% | 21.9% | 20.1% | **19.0%** |
| Mục lục in sẵn bỏ | 3 dòng | 12 | 12 dòng | 12 dòng |
| epubcheck | HỢP LỆ | HỢP LỆ | HỢP LỆ | **HỢP LỆ** |
| Tất định (2 lần build) | ✓ | ✓ | ✓ byte-identical | **✓ byte-identical** |

> Số ở cột v2/v3 đo cùng cách (ký tự = text đã strip tag trong các file XHTML nội dung; độ phủ =
> ký tự EPUB / 366 215 ký tự lớp chữ PDF). Cột "sau sửa (v2)" là 351 337/95.9% như bản ghi trước.

**Trước khi sửa (1b đầu)**: Docling chỉ phủ **75.2%** chữ — mất ~25% nội dung thật vì coi **khung chữ
là "picture"** (chỉ cắt ảnh). 106 trang < 70%, 28 trang rỗng (vd trang 23: 2767 ký tự → 0).

**Sau khi sửa (bước 1–4)**:
- **Khôi phục chữ trong picture** (đọc lớp chữ PDF trong bbox): độ phủ **75.2% → 95.9%** (≈ 96.3% so
  với heuristic). Phần còn thiếu chủ yếu là **mục lục in sẵn** (trang 9–11) — đã cố ý bỏ — và vài
  trang bìa/giới thiệu.
- **Gộp chương**: 721 → **7 file** (chỉ cắt theo kích thước + heading cấp cao hiếm; 720 heading vẫn
  là mục nav qua anchor).
- **Nén ảnh**: 71 MB → **2.7 MB** (JPEG q80, cạnh ≤ 1200 px; bỏ ảnh tí hon < 64 px).

**Còn lại / đánh đổi**: Docling vẫn ~**43 giây/cuốn** (CPU) và kéo theo dep nặng; chất lượng chữ bị
chặn bởi OCR gốc (ABBYY). Nếu OCR gốc kém → cân nhắc OCR lại `vie` (US-A7).

### v3 — Lọc dòng rác (âm tiết Việt) + bỏ tiêu đề chạy đầu trang (`PIPELINE_VERSION 3`)

Hai bước hậu xử lý trên danh sách khối (áp **sau** Docling/heuristic, **trước** khi dựng EPUB):

- **Lọc dòng rác theo âm tiết Việt** (cả hai engine): chấm mỗi khối chữ = tỷ lệ token là âm tiết
  tiếng Việt hợp lệ (bỏ qua số/dấu câu đứng riêng; token có chữ Hán = hợp lệ). Khối điểm < **0.5**
  **và ngắn** (heading hoặc ≤ 60 ký tự) → bỏ; khối **dài** điểm thấp → **giữ** nhưng cảnh báo.
- **Bỏ tiêu đề chạy đầu trang** (đường Docling): tiêu đề (hoặc khối ngắn) ở **đầu trang** trùng nội
  dung (sau khi bỏ chữ số, hạ thường — tái dùng `_band_key` của heuristic) trên **≥ 3 trang** →
  giữ lần đầu, bỏ các lần sau.

Ba chỉ số yêu cầu (so **v2 → v3**, đo cùng cách):

- **Khối rác bỏ**: **27** khối (+ **10** tiêu đề chạy đầu trang lặp "ĐÔNG Y VÀ BÍ QUYẾT DƯỠNG SINH
  BỐN MÙA").
- **Heading trước/sau**: **720 → 703** (bỏ 10 header lặp + 7 heading rác; các tên mục thật như
  "DƯỠNG SINH MÙA THU", "THỂ CHẤT KHÍ HƯ", "KINH MẠCH LÀ GÌ?" được **giữ nguyên**).
- **Độ phủ chữ**: **95.9% → 95.7%** (giảm **0.17 điểm %**, dưới ngưỡng ~1%). EPUB vẫn **2.7 MB**,
  **tất định** byte-identical, **epubcheck HỢP LỆ**.

**27 khối rác bỏ** chủ yếu là ký hiệu trang trí OCR (`?>?H$ 4 í im Àub1$ *íhA`, `= = ^ s -`,
`<*x>o-c*x>o<xx>…`) và vài mảnh tiêu đề bìa vỡ (`TƯ HỌC PHƯỢNG p ị ịặ…`, `TỰHỆE BỐNGY`). **Cần người
xác nhận loại oan**: một cụm là **thông tin xuất bản** (địa chỉ, ĐT, Fax, email, website nhà in — vd
`18 Lê Lai -Tp. Pleiku…`, `Email: info@huyhoangbook.vn`, `www.huyhoangbook.com.vn`) — là chữ thật
nhưng không phải nội dung đọc; bị bỏ vì tỷ lệ âm tiết Việt thấp. Nếu muốn giữ colophon thì nâng
ngưỡng/ bỏ qua dòng có email/URL.

## Phụ lục — số liệu máy chạy
`summary.json`: `seconds=41.07`, `seconds_per_page=4.11`, `n_pictures=10`, `ocr_used=false`
(macOS, CPU; lần đầu tải thêm model layout ~vài chục MB).
