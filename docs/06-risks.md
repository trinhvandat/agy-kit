# 06 — Rủi ro & Spike (Risks & Mitigations)

> Cập nhật: 2026-10-26. Mỗi rủi ro lớn kèm **spike** (thử nghiệm nhỏ) nên làm **trước** khi cam kết.
> Spike gắn với **mốc (milestone)** trong [07-roadmap.md](./07-roadmap.md), không gắn với "tuần".

## Thang đánh giá
- **Khả năng**: Thấp / Trung bình / Cao
- **Tác động**: Thấp / Trung bình / Cao / Nghiêm trọng (chặn dự án)

---

## R-01 — foliate-js / WebView bridge & nạp file local bất ổn (★ rủi ro số 1)

- **Khả năng**: Cao · **Tác động**: Nghiêm trọng
- **Vì sao**: foliate-js tự nhận API "không ổn định"; phải tự bắc cầu JS↔Kotlin (chọn vùng, highlight, đồng bộ CFI, cử chỉ lật trang); WKWebView (iOS) khác Android WebView.
- **Rủi ro nạp file local (đã kiểm tra source `compose-webview-multiplatform`)**: thư viện **không** tích hợp `WebViewAssetLoader` (Android) / `WKURLSchemeHandler` (iOS); mặc định `file://` → foliate-js (fetch/Blob) **dễ bị chặn CORS**. Phải **tự cấu hình** asset loader/scheme handler qua raw WebView (`onCreated`). iOS: scheme handler phải đăng ký **trước khi tạo WKWebView** (onCreated chạy sau) → có thể cần tùy biến factory. iOS từng có lỗi render trắng khi nạp từ file (#230).
- **Giảm thiểu**:
  - Vendor foliate-js **pin SHA** (không auto-update).
  - Bọc sau interface `ReaderEngine` → đổi sang Readium không sửa UI/data.
  - Giới hạn bề mặt bridge: loadBook, goTo(cfi), currentCfi, selectionRange(+prefix/suffix), addHighlight, removeHighlight, applyTheme.
  - EPUB lớn: **phục vụ file `.epub` qua asset loader local** (foliate-js tự giải nén zip trong JS), tránh base64 qua bridge; chỉ giải nén sẵn nếu zip/range trong WebView gặp vấn đề (xác minh trong SPIKE-1).
- **🔬 SPIKE-1 (Mốc 2, bắt buộc)**: nhúng foliate-js vào `compose-webview-multiplatform`, tự cấu hình asset loader local, mở 1 EPUB tiếng Việt. Checklist:
  - lật trang; lấy CFI vị trí; chọn 1 đoạn → nhận CFI range + prefix/suffix; tô highlight;
  - **app chèn font theo `VariantConfig` (serif + CJK phồn thể) vào WebView** và kiểm tra chữ Hán hiển thị (pipeline chỉ ghi `font-family: serif`, app mới quyết định font thật);
  - **re-anchor bằng `search` của foliate-js qua bridge (ADR-008)**: tìm `prefix+snippet+suffix` sau khi **NFC + gộp khoảng trắng** → trả CFI mới; thử với một EPUB đã build lại (cấu trúc khác) để xác nhận highlight + vị trí đọc nhảy đúng chỗ.
  - **Dự phòng khi `search` không khớp chuỗi dài vắt qua hai đoạn**: foliate-js `search` có thể trượt nếu `prefix+snippet+suffix` vắt qua ranh giới đoạn/thẻ. → tìm **chỉ `textSnippet`** (chuỗi ngắn, ít vắt đoạn), rồi **xác nhận bằng `prefix`/`suffix` phía Kotlin** (so khớp văn bản lân cận quanh kết quả); nếu nhiều kết quả thì chọn cái gần `progress` nhất. Thử nghiệm cả hai cách trong spike.
  - **Làm trên Android trước.** Phần iOS **time-box tối đa ~6 giờ** và **không chặn** việc dùng app hằng ngày trên Android.
  - **Checklist iOS riêng**: xác nhận **lớp phủ Compose vẽ đè WKWebView** (qua interop) hiển thị đúng (độ ấm/độ sáng), **và** thao tác **chạm xuyên qua lớp phủ** để lật trang/chọn chữ trong WKWebView vẫn hoạt động (đây là điểm iOS dễ khác Android).
  - **Cửa quyết định ADR-001**: dựa trên **kết quả Android** + kết quả iOS trong khung giờ. Nếu Android ổn nhưng iOS bế tắc trong 6h → vẫn tiến trên Android, ghi nợ iOS, cân nhắc Readium cho iOS sau.
- **Trạng thái (2026-10-26, Mốc 2): ĐÓNG — cửa quyết định ADR-001 giữ foliate-js.** Đã **kiểm thực tế trên
  emulator Android (API 36)**: nhập EPUB qua SAF, foliate-js **render EPUB tiếng Việt trên nền sepia**, **lật
  trang** (chạm phải), **nhớ vị trí** (thoát/mở lại đúng trang, bền qua cài lại APK). compose-webview-multiplatform
  2.0.3 (build Kotlin 2.1.20/CMP 1.8.0) chạy OK trên dự án 2.4.20/CMP 1.12.2. Đã sửa: thiếu `vendor/zip.js`
  (EPUB không mở), race `bridgeReady` (chờ kmpJsBridge + ping). **Còn một cảnh báo JS `appendChild` benign**
  từ lớp inject bridge của thư viện (không chặn chức năng). **iOS vẫn mở** (WKURLSchemeHandler chưa làm — issue #3).
  **Chọn chữ/highlight** là nợ Mốc 3 (lớp chạm Compose chặn nhấn-giữ). Re-anchor **xuyên-build** chưa kiểm (chưa
  có mẫu EPUB build-lại khác cấu trúc).

## R-02 — Build iOS lần đầu (bạn chưa từng làm)

- **Khả năng**: Cao · **Tác động**: Cao
- **Vì sao**: cần macOS + Xcode, signing, chạy simulator/thiết bị; expect/actual cho WKWebView, scheme handler, UIDocumentPicker, file paths.
- **Giảm thiểu**: Android trước (dogfood ngay); iOS chạy **song song ở mức "hello world + mở 1 sách"** sớm để lộ vấn đề toolchain; dùng KMP template chuẩn JetBrains. **Mọi việc iOS cộng thêm thời gian trong roadmap**.
- **🔬 SPIKE-2 (Mốc 0–1)**: dựng app KMP rỗng từ template, chạy được trên iOS simulator trước khi thêm tính năng.
- **Trạng thái (2026-10-26)**: **còn mở** — **chưa build iOS lần nào**. `iosApp/` mới có **vỏ SwiftUI** (`iOSApp.swift`, `ContentView.swift`, `Info.plist`) + `iosMain`, **chưa có `.xcodeproj`** (máy chưa cài Xcode). Android đã xong & chạy trên emulator. Theo dõi ở **[issue #3](https://github.com/trinhvandat/sepia/issues/3)**.

## R-03 — Chuyển TCVN3/VNI → Unicode sai dấu

- **Khả năng**: Trung bình–Cao · **Tác động**: Cao (sai dấu = sách vô dụng)
- **Vì sao**: không có package Python chín (nhất là VNI); phải port bảng; dấu kết hợp dễ sai; font có thể bị **đổi tên**.
- **Giảm thiểu**: port bảng từ vietnameseConverter (TCVN3) + VietUnicode (VNI); chuẩn hóa NFC; nhận diện font bằng regex có tiền tố subset + heuristic thống kê; chuyển **theo span sau khi trích** (ADR-005); metric kiểm ký tự rác trong `quality.py`.
- **🔬 SPIKE-3 (Mốc 1)**: 1 trang TCVN3 + 1 trang VNI từ sách thật, chuyển và **so dấu bằng mắt**. Nếu VNI quá khó → tạm xử lý thủ công/loại sách VNI khỏi phạm vi đầu (điểm cần bạn duyệt).

## R-04 — Chất lượng reflow (header/footer sót, ghép đoạn sai)

- **Khả năng**: Trung bình · **Tác động**: Trung bình
- **Vì sao**: PDF đủ loại layout.
- **Giảm thiểu**: tiếng Việt viết rời từng âm tiết → **hầu như không có từ ngắt dòng bằng gạch nối**; **bỏ** de-hyphenation (pd3f/dehyphen/malti/prettyparser), **chỉ ghép dòng thành đoạn**, và **không xóa nhầm gạch ngang thật**. Kiểm tra nhẹ bằng `quality.py` (số đoạn, độ dài đoạn bất thường) + đọc ngẫu nhiên N trang. Chấp nhận sửa tay nhẹ (bán tự động).
- **🔬 SPIKE-4 (Mốc 1)**: chạy pipeline trên **3 cuốn đại diện** (1 text sạch, 1 nhiều cột/bảng, 1 font cũ), **đọc thử bằng KOReader**, quyết định PyMuPDF vs Docling cho từng loại.

## R-05 — Trang ảnh (hình/sơ đồ/bảng) hỏng khi reflow

- **Khả năng**: Trung bình · **Tác động**: Trung bình
- **Giảm thiểu**: phát hiện trang ảnh → nhúng **nguyên trang thành ảnh** trong EPUB (US-A6), không ép reflow bảng/sơ đồ. Xem lại PDF gốc trong app chuyển giai đoạn sau (US-F4).

## R-06 — Hiệu ứng lật trang / hiệu năng trong WebView

- **Khả năng**: Trung bình · **Tác động**: Trung bình
- **Giảm thiểu**: mục tiêu NFR-1 (<150ms/lật); bắt đầu lật **không animation** (hoặc fade nhẹ), thêm hiệu ứng sau; đo trên thiết bị thật (nhất là iOS).

## R-07 — An toàn dữ liệu ghi chú & highlight trôi khi build lại EPUB

- **Khả năng**: Trung bình · **Tác động**: Cao
- **Vì sao**: pipeline còn chỉnh nhiều lần; mỗi lần build lại EPUB, cấu trúc đổi → **CFI cũ trỏ sai** → highlight trôi/mất.
- **Giảm thiểu**:
  - Nhận ra "cùng một cuốn" qua **`bookUid`** (`dc:identifier` ổn định) khi nhập bản build lại (xem [04-data-model.md](./04-data-model.md) §6).
  - Mỗi highlight lưu `textSnippet` + `prefix` + `suffix` (kiểu W3C `TextQuoteSelector`) + `contentHash` + `progress`; **vị trí đọc** cũng lưu `positionSnippet/prefix/suffix` để re-anchor được.
  - **Thuật toán re-anchor** khi mở/nhập sách (dùng chung cho highlight + vị trí đọc): contentHash khớp → dùng CFI; không khớp → tìm `prefix+snippet+suffix`; không thấy → tìm gần đúng quanh `progress`; vẫn thất bại → đánh dấu **orphan**, **không xóa**, vẫn xuất Markdown (xem [04-data-model.md](./04-data-model.md) §3).
  - **Chạy trong JS** bằng `search` của foliate-js qua bridge, NFC + gộp khoảng trắng (ADR-008) — không parser EPUB phía Kotlin; có **dự phòng tìm `textSnippet` + xác nhận `prefix`/`suffix`** (xem R-01).
  - DB transactional; **xuất Markdown + xuất file DB** để sao lưu.

## R-08 — License AGPL của PyMuPDF/ebooklib khi thương mại hóa

- **Khả năng**: Thấp (giai đoạn đầu) · **Tác động**: Cao (nếu bán sau)
- **Giảm thiểu**: giữ pipeline **tách rời**, app không link AGPL; nếu bán → Docling (MIT) hoặc commercial PyMuPDF (ADR-004).

## R-09 — Phạm vi phình to (một người, 10h/tuần)

- **Khả năng**: Cao · **Tác động**: Trung bình
- **Giảm thiểu**: bám roadmap theo **mốc**, mỗi mốc ra 1 bản dùng được ([07-roadmap.md](./07-roadmap.md)); tính năng nhóm F đóng băng ở giai đoạn đầu.

## R-10 — kotlinx-datetime pre-1.0 & Room 3.0 alpha

- **Khả năng**: Thấp · **Tác động**: Thấp
- **Giảm thiểu**: pin phiên bản; nếu cần, dùng kotlinx-datetime 0.7.1; đã chọn SQLDelight nên Room 3.0 alpha ít liên quan.

## R-11 — Kho PDF chủ yếu là scan (OCR phải lên sớm)

- **Khả năng**: Chưa rõ (phụ thuộc SPIKE-0) · **Tác động**: Cao nếu xảy ra
- **Vì sao**: nếu phần lớn kho là scan, pipeline "text layer" gần như vô dụng → **OCR (US-A7) phải lên giai đoạn đầu**, làm phình phạm vi.
- **Giảm thiểu**: **SPIKE-0 chạy đầu tiên** — chạy lệnh `detect` trên **vài sách mẫu** (`samples/`) để ước lượng tỷ lệ scan. Nếu mẫu nhiều scan → nâng US-A7 lên đầu (OCRmyPDF + Tesseract `vie`, hoặc Surya/PaddleOCR cho scan mờ/font cũ), cập nhật [01-requirements.md](./01-requirements.md) §3, [03-pdf-pipeline.md](./03-pdf-pipeline.md), [07-roadmap.md](./07-roadmap.md). *(Mẫu ít → tín hiệu định hướng; nghi ngờ thì thêm mẫu rồi chạy lại.)*

---

## Thứ tự spike đề xuất (làm trước khi commit kiến trúc)
0. **SPIKE-0** (`detect` trên sách mẫu) — **làm đầu tiên**, quyết định OCR có lên sớm không (R-11).
1. **SPIKE-2** (template KMP chạy Android + iOS) — gỡ rủi ro toolchain sớm.
2. **SPIKE-1** (foliate-js + asset loader local + CFI + highlight; **Android trước, iOS time-box 6h**) — **cửa quyết định ADR-001** (R-01).
3. **SPIKE-3** (TCVN3 + VNI → Unicode, 1 trang mỗi loại).
4. **SPIKE-4** (reflow 3 cuốn đại diện, đọc thử bằng KOReader, chấm điểm nhẹ).

> Nếu SPIKE-1 bế tắc trên iOS trong khung giờ: **vẫn tiến trên Android** (dogfood không bị chặn), ghi nợ iOS và đánh giá lại ADR-001 (Readium cho iOS) ở mốc sau. Đây là điểm kiểm soát rủi ro lớn nhất của dự án.
