# 01 — Yêu cầu (Requirements)

> Dự án: **Sepia** — app đọc sách kiểu Kindle cho người học Đông y.
> Giai đoạn: **Thiết kế** (chưa code app). Tài liệu để duyệt.
> Cập nhật: 2026-10-26.

## 0. Bối cảnh & người dùng

- Người dùng chính (và duy nhất lúc đầu): bạn — người học Đông y, có nhiều sách PDF.
- Vấn đề: đọc PDF trên điện thoại chữ quá nhỏ (fixed-layout), đọc trên máy tính mỏi mắt và bất tiện.
- Mục tiêu: tự build một app đọc sách **reflow** (chữ tự dàn theo màn hình), giao diện dịu mắt, dùng hằng ngày (dogfooding), vừa dùng vừa cải tiến.
- Tầm nhìn xa (chưa làm ngay): bán cho sinh viên Đông y năm 1–2; nhân bản kiến trúc sang các biến thể app khác (ngoại ngữ song ngữ, ôn thi…).

### Hồ sơ người dùng (ảnh hưởng thiết kế)
- Thiết bị: **có cả Android lẫn iPhone** → làm Android trước (dogfood ngay trên Android), iOS là đích cuối, không bỏ.
- Kỹ năng: vững **Java backend**, từng làm **KMP cho Android**, **chưa từng build iOS** → các việc iOS phải **cộng thêm thời gian**; rủi ro toolchain iOS (xem [06-risks.md](./06-risks.md) R-02).
- Quỹ thời gian: **~10 giờ/tuần** → roadmap chia theo **mốc (milestone)**, mỗi mốc ước tính tổng giờ và ra được một bản dùng được (xem [07-roadmap.md](./07-roadmap.md)).
- Kho PDF: **đủ loại** — sách có chữ (text layer), sách có ảnh (sơ đồ huyệt vị, bảng biểu), có thể có sách dùng **font cũ TCVN3/VNI** (rút chữ ra bị lỗi ký tự). **Cần kiểm kê kho thật trước khi thiết kế pipeline chi tiết** (SPIKE-0 — xem [06-risks.md](./06-risks.md), [03-pdf-pipeline.md](./03-pdf-pipeline.md)).

## 1. User Stories (theo thứ tự ưu tiên)

### Nhóm A — Chuyển PDF sang EPUB sạch (ưu tiên 1, chạy trên máy tính)
- **US-A0**: Là người dùng, tôi muốn **quét toàn bộ kho PDF** và phân loại mỗi cuốn (`text_unicode | legacy_tcvn3 | legacy_vni | scan | mixed`) kèm thống kê, để biết pipeline cần ưu tiên gì (SPIKE-0).
- **US-A1**: Là người dùng, tôi muốn chạy một script trên máy tính để biến một PDF thành EPUB reflow, để đọc với chữ tự dàn.
- **US-A2**: Là người dùng, tôi muốn script **tự phát hiện** PDF là loại có chữ / scan ảnh / dùng font TCVN3–VNI, để chọn đúng cách xử lý.
- **US-A3**: Là người dùng, tôi muốn chữ bị mã hóa font cũ (TCVN3/VNI) được **chuyển sang Unicode** đúng, để không còn lỗi ký tự.
- **US-A4**: Là người dùng, tôi muốn script **bỏ header/footer/số trang** và **ghép dòng thành đoạn**, để văn bản liền mạch.
- **US-A5**: Là người dùng, tôi muốn script **nhận diện tiêu đề** để tạo **mục lục (TOC)** trong EPUB.
- **US-A6**: Là người dùng, tôi muốn các **trang có hình huyệt vị / bảng biểu** được **render thành ảnh nhúng vào EPUB** (giữ nguyên thông tin đồ họa, không ép reflow).
  - *Giai đoạn đầu chỉ nhúng ảnh.* Chức năng **"xem lại PDF gốc" trong app** (cần `PdfRenderer`/`PDFKit`, và file PDF phải có trên điện thoại) → **chuyển giai đoạn sau** (xem B2, [02-architecture.md](./02-architecture.md)).
- **US-A7** *(điều kiện — xem Ngoài phạm vi §3)*: OCR cho PDF scan (tiếng Việt). Mặc định "để sau", **nhưng** nếu SPIKE-0 cho thấy **scan chiếm phần lớn kho**, US-A7 được **nâng lên giai đoạn đầu**.

### Nhóm B — Đọc sách (ưu tiên 2)
- **US-B1**: Chia trang theo màn hình (pagination), chạm **trái/phải** để lật trang.
- **US-B2**: **Nhớ vị trí đọc** (resume đúng chỗ) — bền vững kể cả sau khi đổi cỡ chữ **và sau khi EPUB được build lại** (re-anchor — xem [04-data-model.md](./04-data-model.md) §3).
- **US-B3**: Chỉnh **cỡ chữ**, **giãn dòng**, **lề**.

### Nhóm C — Giao diện dịu mắt (ưu tiên 3)
- **US-C1**: Chọn **theme** trong 5 bảng màu (Paper, Sepia, E-ink, Sage, Night). Không trắng tinh, không đen tuyền. (Màu chữ/nền áp bằng **CSS** trong WebView.)
- **US-C2**: Thanh **"độ ấm"** (lớp phủ màu cam) và **"độ sáng"** (lớp phủ tối) riêng trong app, độc lập với độ sáng hệ điều hành. **Hiện thực bằng lớp phủ Compose phủ toàn app** (không chặn thao tác chạm), không làm trong WebView (xem C4, [02-architecture.md](./02-architecture.md)).
- **US-C3**: Font **serif** hỗ trợ đầy đủ tiếng Việt (Literata, Noto Serif…). **Vì sách Đông y có chữ Hán (chủ yếu phồn thể)**, CSS phải có **font dự phòng CJK phồn thể** (`Noto Serif CJK TC`, hoặc **font CJK hệ thống** của thiết bị để khỏi nhúng font nặng) để không mất glyph chữ Hán (xem [03-pdf-pipeline.md](./03-pdf-pipeline.md) §8).

### Nhóm D — Highlight & ghi chú (ưu tiên 4)
- **US-D1**: Highlight **nhiều màu**.
- **US-D2**: Ghi chú **gõ phím** gắn với đoạn được highlight.
- **US-D3**: **Xuất ghi chú ra Markdown** ngay từ bản đầu — để **không bao giờ mất dữ liệu**.

### Nhóm E — Thư viện sách (ưu tiên 5)
- **US-E1**: Thêm (nhập file EPUB vào app) / xóa sách. Khi nhập **bản build lại của một cuốn đã có** (cùng `bookUid` = `dc:identifier` ổn định do pipeline ghi), app **thay file và giữ nguyên vị trí đọc + highlight** (chạy re-anchor), không tạo cuốn trùng (xem [04-data-model.md](./04-data-model.md) §6).
- **US-E2**: Sắp xếp (theo tên, ngày thêm, tiến độ…).
- **US-E3**: Hiển thị **tiến độ đọc** mỗi cuốn.

### Nhóm F — Về sau (chưa làm ngay)
- **US-F1**: Gom ghi chú xuyên nhiều cuốn theo **chủ đề** (kinh lạc, tạng phủ, huyệt vị, bệnh chứng). *(Khi làm US-F1 mới thêm lại Tag/Topic vào data model — xem [04-data-model.md](./04-data-model.md).)*
- **US-F2**: Tra **huyệt**.
- **US-F3**: Tra **từ Hán Việt**.
- **US-F4**: Xem lại **PDF gốc** trong app (chuyển từ US-A6).

## 2. Yêu cầu phi chức năng (Non-functional)

| Mã | Yêu cầu | Mục tiêu cụ thể |
|----|---------|-----------------|
| NFR-1 Hiệu năng | Lật trang mượt | Lật trang < 150ms; mở sách < 2s với sách ~500 trang |
| NFR-2 Offline | Chạy hoàn toàn offline | Không cần mạng để đọc/highlight/ghi chú; không tài khoản |
| NFR-3 An toàn dữ liệu ghi chú | Không bao giờ mất ghi chú | (a) DB transactional; (b) re-anchor + highlight mồ côi không bị xóa; (c) **xuất Markdown**; (d) **xuất cả file DB** để sao lưu (xem [04-data-model.md](./04-data-model.md)) |
| NFR-4 Bảo trì | Một người làm được | Ít phụ thuộc, module ranh giới rõ, ưu tiên giải pháp đơn giản |
| NFR-5 Chia sẻ code | Android + iOS chung codebase | Tối đa hóa commonMain; phần native tối thiểu |
| NFR-6 Bảo mật dữ liệu | Dữ liệu cá nhân nằm trên máy | Không gửi nội dung sách/ghi chú ra ngoài; không telemetry |
| NFR-7 Khả năng nhân bản | Tách lõi/nội dung/thương hiệu | Giữ ranh giới (object `BrandConfig`); chưa dùng flavor/target (xem [05-tech-decisions.md](./05-tech-decisions.md) ADR-007) |
| NFR-8 Khả chuyển dữ liệu | Không khóa người dùng | EPUB chuẩn (đọc được bằng app khác) + ghi chú Markdown + DB xuất được |

## 3. Ngoài phạm vi (Out of scope) — giai đoạn đầu

- Lên App Store / Google Play, cơ chế tài khoản, thanh toán, bản quyền số (DRM/LCP).
- Đồng bộ đám mây (cloud sync) nhiều thiết bị. *(Xuất Markdown + xuất DB + copy file là đủ lúc đầu.)*
- **OCR cho PDF scan (US-A7)** — mặc định để sau. **Cửa quyết định (A2)**: nếu **SPIKE-0** cho thấy scan chiếm phần lớn kho PDF thật của bạn, OCR **phải** đưa lên giai đoạn đầu (cập nhật cả [03-pdf-pipeline.md](./03-pdf-pipeline.md), [06-risks.md](./06-risks.md) R-11, [07-roadmap.md](./07-roadmap.md)).
- Tra huyệt / tra Hán Việt / gom ghi chú theo chủ đề (giai đoạn sau).
- **Xem lại PDF gốc trong app (US-F4)** — giai đoạn sau.
- Chuyển PDF→EPUB **ngay trên điện thoại** (giai đoạn đầu chạy bằng script Python trên máy tính).
- Text-to-speech, media overlays, đọc PDF fixed-layout nâng cao — tối giản lúc đầu.

## 4. Giả định & ràng buộc

- Sách là **không DRM** (sách cá nhân) → không cần Readium LCP (xem [05-tech-decisions.md](./05-tech-decisions.md)).
- Chuyển đổi PDF là **bán tự động**: script làm phần nặng, bạn kiểm tra/sửa tay vài chỗ mỗi cuốn.
- **Hai nhánh làm việc song song** (xem [07-roadmap.md](./07-roadmap.md) A3):
  - **Nhánh Pipeline**: EPUB xuất ra **đọc kiểm chứng ngay bằng app có sẵn** (KOReader / Google Play Books / Apple Books) để đánh giá chất lượng reflow — không phải chờ app Sepia.
  - **Nhánh App**: Sepia thay thế dần app đọc có sẵn.
- Ưu tiên **chất lượng đọc thật** hơn số lượng tính năng.

## 5. Tiêu chí hoàn thành (Definition of Done cho giai đoạn đầu)

- **Nhánh Pipeline**: chuyển được ít nhất **3 cuốn Đông y thật** thành EPUB reflow, chữ tiếng Việt đúng dấu (và chữ Hán hiển thị được), **mở đọc tốt trong một app EPUB có sẵn** (vd KOReader).
- **Nhánh App**: mở các EPUB đó trong Sepia, đọc dịu mắt với theme Sepia, **nhớ đúng vị trí đọc kể cả sau khi build lại EPUB**.
- Highlight + ghi chú, **xuất được Markdown + xuất được DB** kiểm chứng bằng mắt.
- Chạy ổn trên **máy Android thật của bạn** (iOS đạt mức "chạy được", hoàn thiện ở mốc sau).
