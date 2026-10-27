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

### Kết quả cả cuốn — v4 (ABBYY) → v5 (hybrid) — ĐÃ HIỆN THỰC

Route `scan_ocr` hybrid đã vào pipeline (`sepia_pipeline/ocr_hybrid.py`, PIPELINE_VERSION 5, ADR-009).
Đo trên **cả cuốn** mẫu (292 trang) bằng `spikes/spike5_v5_measure.py` (cache OCR từ lệnh `ocr`):

| Chỉ số | v4 (Docling + lớp ẩn ABBYY) | **v5 (hybrid Docling + Vision)** |
|---|---|---|
| **WER** p23 / p101 / p186 (GT) | 24.31 / 11.15 / 7.37 % | **4.36 / 2.08 / 3.38 %** |
| **CER** p23 / p101 / p186 | 6.89 / 3.70 / 2.50 % | **1.76 / 0.54 / 1.20 %** |
| Âm tiết sai cấu trúc (toàn cuốn) | 2.58 % | **0.54 %** |
| Độ phủ chữ (so lớp ẩn PDF) | 95.38 % | **107.46 %** (đọc thêm chữ trong hình) |
| Heading / đoạn / ảnh | 712 / 1712 / 180 | 720 / 1726 / **163** |
| Dòng Vision vắt ≥2 khối (cross) | — | **15** |
| Thời gian trích (Docling, CPU) | 35.8 s | 39.2 s *(+ ingest OCR ~5 phút/cuốn, một lần)* |
| Build 2 lần **byte-identical** | ✓ | **✓** |
| epubcheck | HỢP LỆ | **HỢP LỆ** |

→ **Đạt cổng chất lượng** (WER 3 trang GT đều **≤ 5 %**). Chữ sách scan đúng hơn hẳn (WER p23 **24→4 %**),
giữ bố cục Docling (reading-order nhiều cột + cắt hình), **tất định**, EPUB **hợp lệ**.

**Lỗi quan trọng đã sửa khi hiện thực**: trang có **sơ đồ**, Docling gộp cả hình + mọi nhãn vào **một
khối `picture`** (không tách nhãn thành khối con). Nếu **sắp lại dòng Vision theo (y, x)** trong khối đó
→ **quét ngang trộn các cột nhãn** (p101 WER vọt lên **29 %**). Sửa: **giữ nguyên thứ tự dòng Vision gốc**
trong mỗi khối (Vision đọc nhiều cột đã hợp lý) → p101 về **2.08 %**.

**Spot-check thứ tự đọc nhiều cột (p23, 10 đoạn, đối chiếu ảnh trang)**: Docling tuyến tính hoá **theo
cột** (xuống hết cột trái → giữa → phải) — hợp lý cho reflow; **9/10 Đạt**, mỗi khối tiểu sử đúng chữ +
nguyên vẹn. **1/10 chưa đạt**: thân bài "Trương Trọng Cảnh" bị Docling đặt **cuối trang**, rời khỏi tiêu
đề của nó (lỗi reading-order của Docling, không phải lỗi chữ). Tiêu đề chạy "TỰ HỌC ĐÔNG Y | 23" đôi chỗ
dính vào heading cột (Docling không gắn nhãn `page_header` ở trang này).

### v5 → v5.1 (PIPELINE_VERSION 6) — **vá rò lớp chữ ABBYY** (nhánh `fix-hybrid-abbyy-leak`)

**Lỗi phát hiện khi soát v5**: độ phủ **107.46%** ở bảng trên **KHÔNG** phải "đọc thêm chữ trong hình"
mà là **rò lớp chữ ẩn ABBYY**. `extract_blocks_hybrid` fallback `text = item.text` (lớp ABBYY khi
`do_ocr=False`) cho **TỪNG KHỐI** không nhận dòng Vision — kể cả trên trang **CÓ cache**. Hệ quả: EPUB
v5 có **395 262** ký tự trong khi **toàn bộ** cache Vision chỉ **366 321** (~8.5k từ ABBYY lọt vào); lỗi
đặc trưng ABBYY (nhiéu/điéu/vđi/Phưdng/xưong) xuất hiện trong EPUB nhưng **0 lần** trong cache; trang 87
có **cả** bản Vision lẫn bản ABBYY (nhân đôi).

**Sửa** (PIPELINE_VERSION 6): trang **CÓ cache** → khối chữ (heading/para/caption) không nhận dòng Vision
nào thì **BỎ** (không lấy `item.text`), picture không chữ Vision → **ảnh không caption**; chỉ trang
**KHÔNG cache** (fallback) mới giữ lớp chữ Docling/ABBYY. Dòng Vision **"trôi"** (không chồng khối Docling
nào ≥20%) **không** còn bị nhét vào khối gần nhất (kéo chữ sang cột khác) mà **gom thành đoạn riêng, chèn
theo vị trí (y)**. Đo lại cả cuốn (`spikes/spike5_v51_measure.py`):

| Chỉ số (cả cuốn, 292 trang) | v5 (rò ABBYY) | **v5.1 / v6 (đã vá)** |
|---|---|---|
| Ký tự (không trắng) trong EPUB | 395 262 (**107%** cache) | **365 118 (≤ cache 366 321)** |
| "Chữ ngoài nguồn" ở khối chữ (từ ∉ cache trang) | nhiều (~8.5k từ) | **0** |
| Token lỗi ABBYY nhiéu/điéu/vđi/Phưdng/xưong | 9 / 7 / 7 / 4 / 4 | **0 / 0 / 0 / 0 / 0** |
| Token `cùa` (18 rò + 2 thật trong cache) | 20 | **2** (= đúng mức cache) |
| Bất biến A: từ khối ⊆ cache trang | — | **ĐẠT** |
| Bất biến B: mỗi dòng cache dùng 1 lần (assigned+floating=11 889=cache) | — | **ĐẠT** |
| Khối chữ rỗng trên trang có cache bị bỏ | — | **36** |
| Build 2 lần byte-identical · epubcheck | ✓ · HỢP LỆ | **✓ · HỢP LỆ** |

→ **Rò ABBYY đã hết** (bất biến A/B đạt, ký tự ≤ cache, token lỗi về mức cache). Đây là mục tiêu chính
của nhánh và **đã đạt**.

**CÒN MỞ (chưa đạt cổng — cần quyết định trước khi merge):**

1. **WER "tính chèn" (GT ↔ toàn trang theo thứ tự output)**: p23 **75.2%** / p101 **22.3%** / p186 **5.2%**
   — **vượt** ngưỡng 5%. Nhưng số này **y hệt v5** (p23 74.6 / p101 22.3 / p186 5.2) → **không** do rò
   ABBYY (số từ output trên 3 trang GT gần như không đổi v5→v6). Phân tích **bag-of-words** (bỏ thứ tự):
   sai nội dung chỉ **4.7–9.4%**, còn WER theo thứ tự tới 75% → **~90% là do THỨ TỰ ĐỌC** lệch so với GT
   chép tay (GT gom @prose rồi @label; trang thực xen kẽ nhiều cột + nhãn quanh sơ đồ). WER cửa-sổ
   (độ chính xác từng khối) vẫn **2–4.5%**. ⇒ Cổng "WER tính chèn ≤5%" như định nghĩa **đo thứ tự**, không
   đo rò chữ; với sách tra cứu nhiều cột gần như không thể đạt trừ khi thứ tự output khớp đúng GT.
2. **Dòng trôi 20.4%** (2 427/11 889 dòng) — **> 5%**. Chẩn đoán: **2 416/2 427** dòng chồng **0%** với
   MỌI khối (không phải "gần ngưỡng"); soi trang 101 thấy toạ độ Vision ↔ Docling **khớp đúng**
   (overlap 0.6–0.99 ở nơi có khối) → **bác** giả thuyết "bbox lệch hệ toạ độ". Nguyên nhân thực:
   **Docling phủ bố cục thưa trên trang scan** (nhiều trang chỉ ra 1 header + 1 `picture`, bỏ sót vùng
   thân chữ) nên dòng Vision thân bài **nằm ngoài mọi khối**; 1 092 dòng trôi gần `section_header`,
   865 gần `text`. Chỉnh ngưỡng/toạ độ **không** giúp (overlap = 0, không phải near-miss). Giảm số này cần
   **đổi chiến lược map dòng→bố cục** khi Docling phủ thưa (vd: trang có khối phủ < X% dòng thì xếp dòng
   trôi thành **một cột theo thứ tự Vision**) — việc lớn hơn phạm vi vá rò, nên **dừng để báo trước khi
   tinh chỉnh tiếp** (đúng yêu cầu brief mục 2).
3. **Bảng (`Table`) vẫn lấy chữ ABBYY**: 2 101 từ trong bảng ∉ cache Vision (route hybrid chưa thay chữ
   bảng bằng Vision). Nằm ngoài "khối chữ" của bất biến A nhưng vẫn là **nguồn ABBYY còn lại**.

### v5.1 → v7 (PIPELINE_VERSION 7) — **bảng mang chữ Vision, bất biến A mở sang ô bảng** (nhánh `fix-hybrid-tables-reanchor`)

**Lỗi còn lại khi soát v6**: bất biến A v6 **chỉ đo heading/para/caption** → **chừa bảng**. Đo lại trên
**TOÀN BỘ text EPUB** (kể cả `<td>`): **41 bảng, ~9.2k từ trong ô bảng là chữ ABBYY** (`nhiéu`×9, `điéu`×7,
`vđi`×7, `Phưdng`×4, `xưong`×3…). Đồng thời dòng Vision vùng bảng **không** chồng khối Docling nào (bảng
không là target) → **"trôi" thành đoạn riêng** → trang 87 có **cả** "những vùng nhiều thịt" (Vision ×2) lẫn
"vùng nhiéu thịt…" (ABBYY trong bảng) ⇒ **nhân đôi**.

**Cách đã chọn** — *gán dòng Vision vào ô theo bbox ô* (hướng ưu tiên của brief, **không** phải fallback
"thay bảng bằng đoạn"): Docling `TableCell` **có `bbox`** + `start_row/col_offset_idx` (đã kiểm). Nên:
bảng trở thành **target** (`_build_targets`) → dòng Vision vùng bảng được **gán vào bảng** (hết trôi nhân
đôi), rồi `_table_rows_from_lines` phân mỗi dòng vào **ô chồng lấn lớn nhất** (dự phòng: ô gần tâm nhất để
**không mất dòng**), chữ ô = nối dòng **theo thứ tự Vision**. Trang **CÓ cache**: ô bảng chỉ lấy chữ
Vision; bảng không nhận dòng Vision nào → **BỎ** (không lấy lưới ABBYY). Trang **KHÔNG cache**: giữ lưới
ABBYY (`_table_rows`) như v4. Bất biến A (và thước đo token/nhân-đôi) **mở sang mọi loại khối có chữ**
(heading, para, caption, **ô bảng**).

Đo lại **cả cuốn, trên TOÀN BỘ text EPUB** (`spikes/spike5_v51_measure.py`, PDF *Tự Học Đông Y*):

| Chỉ số (cả cuốn, 292 trang — đo TOÀN BỘ text EPUB) | v6 (bảng ABBYY) | **v7 (bảng Vision)** |
|---|---|---|
| Bất biến A: **mọi** từ khối trang-cache ⊆ cache (kể cả ô bảng) | HỎNG (bảng ~9.2k từ ABBYY) | **ĐẠT — 0 từ ngoài nguồn (bảng = 0)** |
| Bất biến B: mỗi dòng cache dùng 1 lần (assigned+floating = 11 889 = cache) | ĐẠT | **ĐẠT** |
| Token lỗi ABBYY vượt mức cache (nhiéu/điéu/vđi/Phưdng/xưong) | > 0 (trong bảng) | **0 / 0 / 0 / 0 / 0** |
| Token `cùa` (EPUB vs cache) | — | **2 = 2 (vượt 0)** |
| Cụm 8 từ nhân đôi Vision+ABBYY (cùng trang, 1 bản ∉ cache) | > 0 | **0** |
| Ký tự (không trắng): EPUB ≤ cache | — | **366 133 ≤ 366 321 ✓** |
| Build 2 lần byte-identical · epubcheck | ✓ · HỢP LỆ | **✓ · HỢP LỆ** |
| Khối (kể cả bảng) rỗng trên trang cache bị bỏ | — | **42** |
| Dòng trôi | 20.4%¹ | **8.33%** (990/11 889) |

¹ *v6 đo dòng trôi gồm cả dòng vùng bảng; v7 gán chúng vào bảng nên dòng trôi giảm còn 8.33% — phần còn lại
chủ yếu nằm cạnh `section_header` (980/990 chồng 0% mọi khối) do Docling **phủ bố cục thưa trên trang scan**
(mục CÒN MỞ #2) — việc riêng, đã mở GitHub issue, nằm ngoài phạm vi nhánh này.*

→ **Nguồn ABBYY còn lại (bảng) đã hết**: bất biến A/B đạt trên toàn bộ text, token lỗi về mức cache, **0**
cụm nhân đôi Vision+ABBYY. WER "tính chèn" 3 trang GT **y hệt v6** (do thứ tự đọc, không do bảng) — không
đổi bởi nhánh này.

## Thiết kế tất định: OCR = **ingest một lần** + **cache** (ĐÃ hiện thực — ADR-009)

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

> **ĐÃ CHỐT → [ADR-009](../05-tech-decisions.md#adr-009--ocr-lại-sách-scan-bằng-apple-vision-lúc-ingest-cache-theo-sách-build-epub-chỉ-đọc-cache)**:
> "OCR = ingest một lần, cache theo `bookUid`+engine+phiên bản; `build_epub` tất định từ cache, không
> OCR trong build". Hiện thực: `sepia_pipeline/ocr_cache.py` + `ocr_vision.py` + `ocr_hybrid.py`; docs/03 §5.1.

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
