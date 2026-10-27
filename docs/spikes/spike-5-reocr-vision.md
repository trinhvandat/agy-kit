# SPIKE-5 — OCR lại **từ ảnh trang** (Apple Vision) vs lớp chữ ẩn ABBYY

> Thử nghiệm, **CHƯA sửa ADR** — chỉ ghi kết quả + đề xuất. Cập nhật: 2026-10-27.
> Tiếp nối SPIKE-4 (dòng "chất lượng chữ bị chặn bởi OCR gốc — cân nhắc OCR lại `vie`").
> Mẫu: `Tự Học Đông Y - Bùi Huy.pdf` (292 trang, **ABBYY FineReader 11**).

## Bối cảnh (đo lại, xác nhận)

PDF mẫu = **ảnh scan nét** + **lớp chữ ẩn** do ABBYY tạo (font Arial vô hình). Cả hai đường pipeline
(heuristic lẫn Docling) đều **chỉ đọc lớp chữ ẩn** → kế thừa lỗi của lớp đó. Lỗi **có hệ thống** của
ABBYY trên mẫu này là nhầm **dấu** (ề/ế→é, ầ→ắ, ớ→đ, ơ→d, ơ→o…): `phương→phưdng`, `Dưới→Dưđi`,
`nhiều→nhiéu`, `đốt→đót`, `trước→trưđc`… Ảnh gốc **đúng**; chỉ lớp chữ sai.

## Câu hỏi spike

- **A (CHÍNH)** — OCR lại **từ ảnh trang** (bỏ lớp chữ ẩn) có cho chữ **đúng hơn rõ rệt** không?
  Chạy **offline trên Mac** mất bao lâu/trang?
- **B (PHỤ)** — nếu A không đủ tốt/quá chậm: sửa chính tả lớp ẩn theo bảng nhầm + từ điển được bao nhiêu?

## Engine chọn để thử: **Apple Vision** (native macOS, 0 cài đặt)

macOS (Darwin 24.x, Sequoia) có **Vision framework** hỗ trợ **tiếng Việt `vi-VT`** ở mức `.accurate`
(kiểm `VNRecognizeTextRequest.supportedRecognitionLanguages()`). Chạy qua `swiftc` có sẵn → **không
cài gì** (không Tesseract/torch/Docling), **offline**, nhanh. Xem `spikes/ocr_vision.swift`.

> `vi-VT` **chỉ** có ở mức `.accurate`; mức `.fast` chỉ có 6 thứ tiếng Latin (không có tiếng Việt).

## Cách chạy

```bash
cd pdf-pipeline
uv run python spikes/spike5_reocr_vision.py "../samples/Tự Học Đông Y - Bùi Huy.pdf"
# tuỳ chọn: ... <pdf> 23 101 160   (danh sách trang 0-based)   env: SPIKE5_DPI, SPIKE5_LEVEL
```

Render trang 300 DPI (PyMuPDF) → OCR bằng Vision → so **tỷ lệ token KHÔNG phải âm tiết tiếng Việt
hợp lệ** giữa lớp ẩn và Vision, trên **cùng tập trang**. Dùng chính
`sepia_pipeline.vietnamese.is_vietnamese_syllable` (bộ lọc rác của pipeline) — **không** ground-truth/CER;
lỗi dấu có hệ thống làm token **hỏng cấu trúc âm tiết** nên đo được bằng tỷ lệ này. Kết quả ở
`pdf-pipeline/out/spike5/` (`summary.json`, `p0023_*.txt`, `p0101_*.txt`, ảnh render).

Mẫu đo: **20 trang** = 2 trang chẩn đoán (p23=in trang 24, p101=in trang 102) + 18 trang rải đều.

## Số liệu (A) — Vision thắng rõ rệt

| | **Lớp ẩn ABBYY** | **Vision (OCR lại từ ảnh)** |
|---|---|---|
| Token chữ (20 trang) | 7 324 | 7 440 |
| Token **có dấu** | 6 212 | 6 400 |
| **Bad-âm-tiết / token có dấu** | **2.03 %** (126) | **0.11 %** (7) |
| Bad-âm-tiết / mọi token | 2.66 % (195) | 0.46 % (34) |
| Thời gian | — (đọc sẵn) | render 0.21s + OCR **0.80s/trang** |

- **Chính xác**: tỷ lệ token-có-dấu hỏng **2.03 % → 0.11 %** — **giảm ~18×** (126 → 7 token). Con số
  **2.03 %** của lớp ẩn **khớp** mức "1.9 %" nêu trong brief → thước đo tin được.
- **Tốc độ**: ~**1.0 giây/trang** (render + OCR) trên Mac, offline → **~5 phút cho cả cuốn 292 trang**.
  Nhanh hơn cả đường Docling hiện tại (~43s/cuốn **trích**, nhưng Docling không sửa được lỗi dấu).
- Spot-check 3 ảnh crop trong `out/review/` (chính các chỗ brief nêu): Vision đọc **đúng**
  `Dưới mỏm gai đốt`, `phương thuốc`, `nhiều` — nơi lớp ẩn cho `Dưđi`, `phưdng`, `nhiéu`.

### Lỗi còn sót của Vision — bản chất khác ABBYY

| | Lớp ẩn ABBYY (p23, trang tệ nhất) | Vision (các trang còn sót) |
|---|---|---|
| Số token hỏng | **41** | 0–3 / trang |
| Kiểu | lỗi **dấu có hệ thống** rải khắp **thân bài** (`phưdng`, `thuóc`, `nhiéu`, `trưđc`, `ngưài`, `triéu`…) | mẩu vỡ/nhãn **hình vẽ** cục bộ (`đn`, `đóđn`, `khinú`, `hàr`, `nghiêr`) |

Lỗi ABBYY **phá chữ thường gặp** → hỏng nghĩa khi đọc/tra/xuất ghi chú. Lỗi sót của Vision chủ yếu là
**nhãn trên sơ đồ huyệt** và mẩu dính dòng — không phải văn xuôi — nên tác hại thấp hơn nhiều.

## Kết luận

- **A = CÓ, rõ rệt.** OCR lại từ ảnh bằng Apple Vision cho chữ đúng hơn ~18× ở token có dấu
  (2.03 %→0.11 %), **~1 giây/trang**, **offline, 0 cài đặt** trên Mac. **A đủ tốt và đủ nhanh.**
- **B không cần làm** như đường chính: A vừa đúng hơn vừa nhanh. Bảng nhầm + từ điển chỉ nên giữ như
  **bộ sửa phụ** cho ~0.11 % sót, hoặc cho máy **không phải Mac** (Vision không có) — không ưu tiên.

## Đánh đổi / rủi ro cần cân trước khi đưa vào pipeline (CHƯA sửa ADR)

1. **Thứ tự đọc & layout**: spike chỉ đo **đúng ký tự**, chưa dựng lại bố cục. Vision trả về **dòng +
   bbox** theo thứ tự quét, chưa chắc đúng với trang **nhiều cột/sidebar/chú thích hình** (điểm yếu
   cũ của heuristic; Docling mạnh ở đây). Hướng tích hợp gọn nhất: **giữ layout của đường hiện tại
   (Docling cho `scan_ocr`), chỉ thay *nội dung chữ* từng dòng** bằng Vision theo khớp toạ độ — không
   bỏ phần reading-order/cắt-hình đã làm tốt ở SPIKE-4.
2. **Tất định (QUAN TRỌNG)**: EPUB phải **tất định bất kể môi trường** (nguyên tắc dự án; xem note
   Pillow runtime-dep). Kết quả Vision **có thể đổi theo phiên bản macOS** → nếu OCR chạy lại mỗi lần
   build thì **phá tính tất định**. Giảm thiểu: coi OCR là **bước ingest một lần**, **cache** văn bản
   (ví dụ sidecar theo `bookUid` + SHA ảnh) rồi build EPUB **tất định từ cache**, không OCR trong build.
3. **Khoá nền tảng**: Vision **chỉ chạy macOS**. Pipeline chạy "trên máy tính" và tác giả dùng Mac →
   chấp nhận được (ADR-004: pipeline tách rời app). Muốn chạy nơi khác → fallback **Tesseract `vie`**
   hoặc **PaddleOCR/Surya** (đã nêu ở R-11), chậm hơn, cần cài.
4. **AGPL**: Vision/Swift là hệ thống Apple (không AGPL). Vẫn render bằng PyMuPDF (AGPL) + dựng EPUB
   bằng ebooklib (AGPL) → ranh giới "pipeline tách rời app" (ADR-004, R-08) **không đổi**.

## Việc nên làm tiếp (nếu chốt hướng OCR-lại-Vision cho `scan_ocr`)

- Dựng **prototype "thay chữ theo dòng"**: Docling/PyMuPDF giữ khối + bbox, Vision cấp chữ, khớp theo
  toạ độ dòng; đo lại độ phủ + đọc thử KOReader.
- Thiết kế **cache OCR theo `bookUid`** để giữ tất định (điểm 2) — ghi vào docs/03 §5 và cân nhắc ADR mới.
- Thêm **mẫu scan khác** (nguồn OCR khác ABBYY, và 1 scan **không có** lớp chữ) để xác nhận Vision
  tổng quát, không chỉ hợp mẫu này.
- Nếu chốt: cập nhật **R-11** (cửa quyết định OCR → có engine khả thi), **docs/03-pdf-pipeline.md §5**,
  và cân nhắc **ADR** "OCR lại bằng Vision cho `scan_ocr` khi lớp OCR gốc kém".

## Phụ lục — máy chạy

`out/spike5/summary.json`: `engine=apple-vision`, `dpi=300`, `level=accurate`,
`ocr_sec_per_page≈0.80`, `render_sec_per_page≈0.21`, `est_full_book_min≈4.9` (macOS Sequoia, Vision
chạy trên Neural Engine/GPU, không cần tải model rời).
