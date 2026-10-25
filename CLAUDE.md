# CLAUDE.md — Sepia

Hướng dẫn cho AI/người làm khi làm việc trong repo này. Chi tiết nằm trong `docs/`.

## Dự án là gì

- **Sepia** — app đọc sách kiểu Kindle (EPUB reflow), giao diện dịu mắt, cho **người học Đông y**.
- **Người dùng**: hiện tại là chính tác giả (dogfooding); tầm xa có thể bán cho sinh viên Đông y.
- **Giai đoạn hiện tại**: **THIẾT KẾ** → sắp sang **implementation**. Tài liệu trong `docs/` là nguồn chân lý; đọc trước khi code.

## Quyết định đã chốt (mỗi dòng → ADR)

- **Nền tảng**: Kotlin Multiplatform + Compose Multiplatform, **Android trước**, iOS sau cùng codebase.
- **Bộ hiển thị EPUB**: foliate-js trong WebView (`compose-webview-multiplatform`), **không** Readium lúc đầu — [ADR-001](./docs/05-tech-decisions.md#adr-001--bộ-hiển-thị-epub-foliate-js-trong-webview-không-readium-lúc-đầu). Tự cấu hình WebViewAssetLoader (Android) / WKURLSchemeHandler (iOS) để tránh CORS `file://`.
- **Database**: SQLDelight (Room là lựa chọn thay thế) — [ADR-002](./docs/05-tech-decisions.md).
- **DI**: Koin — [ADR-003](./docs/05-tech-decisions.md).
- **Pipeline PDF→EPUB**: chạy bằng **Python trên máy tính** (không trên điện thoại); PyMuPDF mặc định & **bắt buộc cho font cũ**, Docling cho sách Unicode phức tạp, dựng EPUB bằng ebooklib — [ADR-004](./docs/05-tech-decisions.md), [ADR-005](./docs/05-tech-decisions.md).
- **License AGPL**: PyMuPDF/ebooklib là AGPL → pipeline **tách rời app**, app KMP **không link** AGPL — [ADR-004](./docs/05-tech-decisions.md), [R-08](./docs/06-risks.md).
- **Thương hiệu**: object `BrandConfig`; **chưa** dùng Gradle flavors/Xcode targets — [ADR-007](./docs/05-tech-decisions.md).

## Cấu trúc thư mục

```
sepia/
├── docs/              # 01..07: requirements, architecture, pipeline, data-model, ADRs, risks, roadmap
├── pdf-pipeline/      # Python CLI (PDF → EPUB) — KHÔNG thuộc app KMP, license AGPL tách biệt
├── composeApp/        # app KMP: commonMain (domain/data/reader/theme/overlay/annotation/feature)
│                      #          androidMain / iosMain (actual tối thiểu)
├── CLAUDE.md          # file này
└── README.md
```

## Nguyên tắc

- **Android trước**: dogfood ngay trên Android; iOS luôn **time-box** và **không chặn** việc dùng hằng ngày.
- **Mỗi mốc ra một bản dùng được** (xem [07-roadmap.md](./docs/07-roadmap.md)); ưu tiên một lát dọc chạy được hơn làm xong một lớp.
- **Không xây "nền tảng cho mọi thứ"**: chỉ giữ ranh giới 3 lớp (lõi / nội dung / brand) đủ sạch để tách sau.
- **Ghi chú luôn xuất được ra ngoài**: Markdown + xuất file DB; highlight không định vị được → đánh dấu "orphan", **không xóa** ([04-data-model.md](./docs/04-data-model.md) §3).
- **Không gửi dữ liệu ra mạng**: offline-first, không tài khoản, không telemetry (NFR-2, NFR-6).
- **Giải pháp đơn giản, ít phụ thuộc, dễ bảo trì một người** (NFR-4).

## KHÔNG làm ở giai đoạn này

- Không viết code app/pipeline khi đang ở bước duyệt thiết kế (trừ khi được yêu cầu).
- Không lên store, không tài khoản/thanh toán/DRM, không cloud sync.
- Không OCR (trừ khi SPIKE-0 cho thấy kho PDF chủ yếu là scan — [R-11](./docs/06-risks.md)).
- Không tra huyệt / tra Hán Việt / gom ghi chú theo chủ đề / xem PDF gốc trong app (nhóm US-F — giai đoạn sau).
- Không dùng Gradle flavors/Xcode targets; chưa tách Gradle module.
- Không làm độ ấm/độ sáng trong WebView (dùng lớp phủ Compose — C4).

## Mốc hiện tại & việc kế tiếp

- **Hiện tại**: hoàn tất bộ tài liệu thiết kế (`docs/` 01–07) — chờ tác giả duyệt.
- **Việc kế tiếp (Mốc 0)**: SPIKE-0 (kiểm kê kho PDF) → quyết định OCR; SPIKE-2 (template KMP chạy Android + iOS). Xem [07-roadmap.md](./docs/07-roadmap.md).
