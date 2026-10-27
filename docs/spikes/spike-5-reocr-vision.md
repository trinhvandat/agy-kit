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

> ⚠️ **Đính chính sau khi đo CER/WER (mục dưới)**: câu "lỗi Vision chủ yếu ở nhãn hình" **chỉ đúng
> một phần**. Vision **vẫn** mắc lỗi **sai 1 dấu thanh trong thân bài** (`Tần→Tân`, `dược→được`,
> `nhiều→nhiếu`, `bệnh→bênh`, `khôi→khi`, `lao→tao`…) — **cùng kiểu** lỗi ABBYY, chỉ **ít hơn ~4×**.

## Soát lại (2026-10-27): thước đo âm tiết **bỏ sót** lỗi — đo CER/WER trên ground truth

**Vấn đề của thước đo gốc.** "Tỷ lệ token không phải âm tiết Việt hợp lệ" **chỉ bắt được** lỗi làm
chữ **hỏng cấu trúc âm tiết** (`phưdng`, `Dưđi`). Nó **bỏ sót toàn bộ** lỗi mà kết quả **vẫn là một
âm tiết hợp lệ**: `phổi→phối`, `nằm→năm`, `mỏm→móm`, `của→cúa`, `dọc→doc`, `và→va`, `dược→được`…
Đây lại chính là **đa số** lỗi còn sót. Vì vậy con số **0.11 %** (và cả **2.03 %** của ABBYY) **không
phải tỷ lệ lỗi thật** — chúng là **cận dưới** rất lỏng.

**Cách đo đúng.** Tự **chép tay ground truth** 3 trang từ ảnh 300 DPI (NFC), tách **văn xuôi** và
**nhãn/chú thích hình**: **p23** (văn xuôi + nhiều cột), **p101** (văn xuôi *nghiêng* + nhãn sơ đồ),
**p186** (chữ thuần một cột). GT ở `pdf-pipeline/spikes/gt/*.txt`. Đo **CER** (ký tự) + **WER** (từ)
bằng Levenshtein, ghép GT↔OCR **theo từng khối** (`rapidfuzz.partial_ratio_alignment`, chịu được
khác thứ tự đọc giữa 2 engine). Script: `spikes/spike5_cer_wer.py` — **không gọi Vision**, đọc văn bản
OCR đã lưu → **chạy được ở CI Ubuntu**.

```bash
cd pdf-pipeline && uv run --with rapidfuzz python spikes/spike5_cer_wer.py   # mặc định trang 23 101 186
```

### Số liệu CER/WER (ground truth, 3 trang — 9 102 ký tự / 1 982 từ)

| Trang | | CER văn xuôi | WER văn xuôi | CER nhãn hình | WER nhãn hình | **CER chung** | **WER chung** |
|---|---|---|---|---|---|---|---|
| **p23** (nhiều cột) | ABBYY | 6.81% | 24.69% | — | — | **6.81%** | **24.69%** |
| | Vision | 3.08% | 5.61% | — | — | **3.08%** | **5.61%** |
| **p101** (nghiêng+nhãn) | ABBYY | 1.70% | 6.02% | 5.88% | 17.39% | **3.54%** | **10.96%** |
| | Vision | 0.15% | 0.67% | 1.04% | 3.91% | **0.54%** | **2.08%** |
| **p186** (chữ thuần) | ABBYY | 2.30% | 7.22% | — | — | **2.30%** | **7.22%** |
| | Vision | 1.20% | 3.38% | — | — | **1.20%** | **3.38%** |
| **Tổng** | **ABBYY** | 4.27% | 15.01% | 5.88% | 17.39% | **4.46%** | **15.29%** |
| **Tổng** | **Vision** | 1.89% | 3.94% | 1.04% | 3.91% | **1.79%** | **3.94%** |

**Lỗi cấp từ** (thay/xoá/chèn, so GT): **ABBYY 242** (222 thay), **Vision 65** (50 thay). Trong số lỗi
"thay", số lỗi mà kết quả **vẫn là âm tiết Việt hợp lệ** (→ **thước đo gốc BỎ SÓT**): **ABBYY 130/222**,
**Vision 43/50**. Tức thước đo âm tiết chỉ "thấy" được **~40 %** lỗi ABBYY và **~14 %** lỗi Vision.

### Diễn giải (trung thực hơn "18×")

- **Vision vẫn thắng rõ**, nhưng mức thật là **CER ~2.5× / WER ~3.9×** (4.46→1.79 %, 15.29→3.94 %),
  **không phải 18×**. Con số 18× là **ảo giác của thước đo mù** (chỉ đếm token vỡ cấu trúc).
- **Chênh lệch lớn nhất ở nơi ABBYY hỏng hệ thống**: trang nhiều cột **p23** (WER 24.7→5.6 %, ~4.4×)
  và nhãn hình **p101** (WER 17.4→3.9 %). Ở **chữ thuần p186** khoảng cách **hẹp lại** (7.2→3.4 %) vì
  **cả hai** cùng vấp **mất ký tự cuối dòng do bóng gáy sách** (scan), không phải lỗi engine.
- **Nhãn/chú thích hình**: Vision tốt hơn hẳn (WER 17.4→3.9 %) — đúng hướng, vì nhãn là nơi app sẽ
  xuất ghi chú/tra cứu.
- **Lỗi còn lại của Vision** (xem `cer_wer.json`) chủ yếu là **sai 1 dấu thanh** (ă/â, ể/ế, ỏ/ó…) rải
  trong **cả thân bài lẫn nhãn** — **cùng bản chất** lỗi ABBYY, chỉ ít hơn. Không phải "chỉ ở nhãn hình"
  như nhận định ban đầu. 10 ví dụ đại diện (kèm loại) ở cuối tài liệu.

## Tích hợp bố cục: Docling + Vision (2026-10-27)

Spike đo "đúng ký tự" chưa dựng bố cục. Thử 2 hướng đưa Vision vào đường `scan_ocr` (giữ reading-order
+ cắt hình của Docling — SPIKE-4). Script: `spikes/spike5_layout.py` (gọn) và `spikes/spike5_hybrid.py`
(hướng 2). Cần `uv sync --extra docling` + `--with ocrmac` (chỉ macOS).

### Hướng A (gọn) — Docling + `OcrMacOptions` (Apple Vision) — **CHẠY ĐƯỢC nhưng chữ TỆ**

Docling **2.142.1 có sẵn** engine Apple Vision (`OcrMacOptions`, `framework="vision"`,
`recognition="accurate"`, `lang=["vi-VT"]`, `force_full_page_ocr=True`). Chạy **1.6s/trang**, bố cục tốt
(**27 hình**/13 trang; p23 reading-order **đúng** — đoạn mở đầu ra trước). **Nhưng text tệ hơn ~10×**:

| | p23 | p101 | p186 |
|---|---|---|---|
| **WER Docling+Vision (gọn)** | **28.93%** | **20.23%** | 10.91% |
| WER Vision chạy thẳng (raw) | 5.61% | 2.08% | 3.38% |

→ Hướng gọn cho chữ **còn tệ hơn cả ABBYY lớp ẩn** (WER chung 15.3%) ⇒ **mất sạch** lợi thế Vision.
**Truy nguyên** (quan trọng): **không** phải lỗi Vision/ocrmac/ngôn ngữ/renderer/DPI — `ocrmac` chạy
thẳng trên ảnh **PyMuPDF _và_ pypdfium2** đều cho **WER ~2%** (p101), và **nâng `scale` lên 300/432 DPI
không cứu được**. Lỗi nằm **bên trong khâu OCR của Docling** (cách nó cắt vùng/ghép cell). ⇒ Hướng gọn
**chưa dùng được** nếu không vá Docling.

### Hướng B (hướng 2 của brief) — **bố cục Docling + chữ Vision theo toạ độ** — **ĐẠT**

Docling(`do_ocr=False`) lấy **khối + bbox + thứ tự đọc**; OCR **cả trang một lần** bằng Vision (chất
lượng raw); gán mỗi **dòng Vision** vào khối Docling **chứa tâm dòng** (bbox chuẩn hoá); xuất theo thứ
tự khối Docling. `spikes/spike5_hybrid.py`:

| Trang | CER | WER | Hình (Docling) | Thứ tự đọc |
|---|---|---|---|---|
| **p23** (nhiều cột) | **1.97%** | **4.49%** | 7 | đoạn mở đầu ra trước ✓ |
| **p101** (nghiêng+nhãn) | **3.20%** | **4.54%** | 1 | ✓ |
| **p186** (chữ thuần) | **1.20%** | **3.38%** | 0 | ✓ |

→ **Chất lượng chữ ≈ Vision raw** (WER ~3.9%), **đồng thời giữ bố cục Docling** (hình + reading-order
nhiều cột). **~2.9s/trang** (Docling layout + 1 lần Vision). **Đây là hướng tích hợp khuyến nghị.**

> Đánh đổi còn lại của hướng B: việc gán dòng→khối theo bbox làm **nhãn nhỏ** đôi chỗ bị tách/gộp
> (p101 WER 4.54% hơi cao hơn raw 2.08%) — chấp nhận được, vẫn **≪** hướng gọn. Có thể tinh chỉnh gán
> theo chồng lấn diện tích thay vì chỉ tâm dòng. Độ phủ chữ (Docling+Vision so lớp ẩn) ~56–120%/trang
> (`fixtures/layout_summary.json`); <100% ở vài trang gần toàn ảnh (p265/p280), >100% khi Vision đọc
> thêm chữ trong hình mà lớp ẩn xếp chỗ khác.

## Thiết kế tất định: OCR = **ingest một lần** + **cache** (CHƯA code vào `convert`)

**Vấn đề**: kết quả Vision **có thể đổi theo phiên bản macOS/Vision** → nếu OCR chạy **mỗi lần build**
thì EPUB **không còn tất định** (phá NFR; đối lập với kết quả byte-identical ở SPIKE-4). Thêm nữa: **CI
Ubuntu không có Vision** → build/test **không được** gọi Vision.

**Nguyên tắc**: tách OCR thành **bước ingest chạy một lần trên Mac**, lưu **cache**; `build_epub` **chỉ
đọc cache**, **không OCR trong build**. Nhờ đó build **tất định trên mọi máy** (kể cả CI Ubuntu) vì
bước phụ-thuộc-nền-tảng duy nhất đã bị đẩy ra khỏi đường build.

**Khoá cache** (một entry = một lần OCR cụ thể):

```
bookUid        = "sepia:" + SHA-256(PDF gốc)         # = dc:identifier, đã có (docs/03 §8, 04 §6)
render         = { dpi: 300 }                         # tham số render ảnh trước OCR
engine         = { name:"apple-vision", recognition:"accurate", lang:["vi-VT"], framework:"vision" }
engine_version = { macos_build:"24E263", vision_langs_sha:"0f6dbcc92f23", ocrmac:"1.0.1" }
cache_key      = SHA-256( bookUid | render | engine | engine_version )
```

**Giá trị cache** (đủ để chạy **hướng B** tất định, KHÔNG cần Vision lúc build) — per-page:

```jsonc
// .ocr_cache/<sha256(pdf)>.json   (NFC, sort_keys → tự tái lập + diff được)
{
  "book_uid": "sepia:…", "pdf_sha256": "…", "render": {...}, "engine": {...},
  "engine_version": {...}, "created": "2026-10-27", "ocr_schema": 1,
  "pages": [ { "page": 23, "lines": [ { "text": "Lịch sử…", "bbox": [x,y,w,h], "conf": 0.97 }, … ] } ]
}
```

> Lưu **dòng + bbox + độ tin** (không chỉ text phẳng) để hướng B (gán dòng→khối Docling theo toạ độ)
> dựng lại **y hệt** từ cache. `spikes/fixtures/*.txt` hiện tại là **PoC rút gọn** của cache này (chỉ
> text); bản thật thêm bbox/conf.

**Hành vi build** (quyết định rõ ràng để giữ tất định):

- **Cache HIT** (`cache_key` khớp engine cấu hình) → build EPUB từ cache.
- **Cache MISS** → **BÁO LỖI** "chạy bước ingest OCR trên Mac trước" — **KHÔNG tự OCR trong build**
  (nếu tự OCR: phá tất định + không chạy được trên Ubuntu/CI).
- **PDF đổi** → `sha256` đổi → `bookUid` mới → entry mới; entry cũ **giữ nguyên** (build cũ tái lập được).
- **Đổi macOS/Vision/engine** → `cache_key` mới; build dùng entry **khớp `engine_version` đang cấu hình**,
  thiếu thì báo lỗi (không im lặng dùng OCR phiên bản khác).

**Vị trí**: sidecar cạnh **pipeline** (không cạnh app; ADR-004 pipeline tách rời). Kho thật **không
commit** (292 trang có thể lớn); **commit mẫu nhỏ** cho test (đúng như `spikes/fixtures/`).

**CI / test (Ubuntu, không Vision)**: nạp **cache fixture** đã commit → build EPUB + `epubcheck` +
kiểm **byte-identical**, **không gọi Vision**. `spikes/spike5_cer_wer.py` (đọc fixtures, không Vision)
đã chứng minh nguyên tắc "test chạy từ cache" khả thi trên CI.

> **Ứng viên ADR mới (CHƯA chốt)**: "OCR = bước ingest một lần, cache theo `bookUid`+engine+phiên bản;
> `build_epub` tất định từ cache, không OCR trong build". Khi chốt hướng → ghi docs/03 §5 + ADR.

## Kết luận

- **Câu hỏi A = CÓ, rõ rệt.** OCR lại từ ảnh bằng Apple Vision cho chữ đúng hơn — đo trên ground truth:
  **WER 15.3 %→3.9 % (~3.9×)**, **CER 4.5 %→1.8 % (~2.5×)** (con số "18×" theo thước đo âm tiết là
  **ảo**, xem mục "Soát lại"). **~1 giây/trang**, **offline, 0 cài đặt** trên Mac. **A đủ tốt và đủ nhanh.**
- **Câu hỏi B (sửa chính tả lớp ẩn) không cần làm** như đường chính: OCR-lại vừa đúng hơn vừa nhanh.
  Bảng nhầm + từ điển chỉ giữ như **bộ sửa phụ** cho phần sót (~3.9 % WER), hoặc cho máy **không phải
  Mac** (Vision không có) — không ưu tiên.
- **Tích hợp bố cục**: dùng **hướng B** (Docling layout + Vision theo toạ độ, `spike5_hybrid.py`) — giữ
  reading-order/hình của Docling **và** chất lượng chữ Vision (WER ~4.5 %). Hướng gọn (Docling+OcrMac)
  **chưa dùng được** (chữ tệ ~10×). Giữ **tất định** bằng **cache OCR** (ingest một lần, build không OCR).

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

- ✅ **ĐÃ LÀM** prototype "thay chữ theo dòng" (`spikes/spike5_hybrid.py`) — xem mục "Tích hợp bố cục"
  hướng B (WER ~4.5%, giữ bố cục). Còn lại: **đọc thử KOReader** + tinh gán bbox theo chồng lấn diện tích.
- Thiết kế **cache OCR theo `bookUid`** để giữ tất định — xem mục "Thiết kế tất định" bên dưới.
- Thêm **mẫu scan khác** (nguồn OCR khác ABBYY, và 1 scan **không có** lớp chữ) để xác nhận Vision
  tổng quát, không chỉ hợp mẫu này.
- Nếu chốt: cập nhật **R-11** (cửa quyết định OCR → có engine khả thi), **docs/03-pdf-pipeline.md §5**,
  và cân nhắc **ADR** "OCR lại bằng Vision cho `scan_ocr` khi lớp OCR gốc kém".

## Phụ lục — máy chạy

`out/spike5/summary.json`: `engine=apple-vision`, `dpi=300`, `level=accurate`,
`ocr_sec_per_page≈0.80`, `render_sec_per_page≈0.21`, `est_full_book_min≈4.9` (macOS Sequoia, Vision
chạy trên Neural Engine/GPU, không cần tải model rời).

## Phụ lục — 10 lỗi Vision còn lại (đại diện, kèm loại)

Trích từ `out/spike5/cer_wer.json` (50 lỗi "thay" của Vision). "Hợp lệ?" = kết quả có là âm tiết Việt
hợp lệ không → nếu **có** thì **thước đo âm tiết gốc bỏ sót** lỗi này.

| # | GT → Vision | Trang / ngữ cảnh | Loại | Hợp lệ? (metric bỏ sót) |
|---|---|---|---|---|
| 1 | `phổi → phối` | p101, thân bài **nghiêng** | sai 1 dấu (ổ→ố); chữ nghiêng khó hơn | ✅ |
| 2 | `nằm → năm` | p101, **nhãn hình** | sai 1 dấu (ằ→ă) | ✅ |
| 3 | `mỏm → móm` | p101, **nhãn hình** | sai 1 dấu (ỏ→ó) | ✅ |
| 4 | `của → cúa` | p101, **nhãn hình** | sai 1 dấu (ủ→ú) | ✅ |
| 5 | `dọc → doc` | p101, **nhãn hình** | mất dấu nặng | ✅ |
| 6 | `dược → được` | p23, thân bài | nhầm phụ âm d→đ | ✅ |
| 7 | `lao → tao` | p23, thân bài | nhầm phụ âm l→t | ✅ |
| 8 | `khôi → khi` | p23, thân bài | mất nguyên âm ô | ✅ |
| 9 | `nhiều → nhiếu` | p23, thân bài | sai 1 dấu (ề→ế) | ✅ |
| 10 | `mùa, ngứa ngáy → mua, ngưa ngày` | p23, thân bài | **chuỗi** nhiều dấu sai (dính dòng) | ❌ |

> **Nhận xét**: 43/50 lỗi "thay" của Vision là **sai 1 dấu nhưng vẫn ra âm tiết hợp lệ** (metric mù).
> Phân bố **cả thân bài lẫn nhãn hình** (không chỉ nhãn). Chữ **nghiêng** (hàng 1) và **nhãn nhỏ**
> (hàng 2–5) là nơi Vision dễ vấp nhất. Một nhóm lỗi **riêng** (không có trong bảng) là **mất ký tự
> cuối dòng sát mép phải do bóng gáy sách** (`sức→sit`, `nên→nêr`, `táo→t°-`…) — **cả ABBYY lẫn Vision
> đều mất như nhau**, là lỗi **scan**, không phải lỗi engine; có thể giảm bằng cách **chừa lề/deskew**
> khi render ảnh trước khi OCR.
