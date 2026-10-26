# CLAUDE.md — Sepia

Hướng dẫn cho AI/người làm khi làm việc trong repo này. Chi tiết nằm trong `docs/`.

## Dự án là gì

- **Sepia** — **bản nền (lõi)** app đọc sách reflow kiểu Kindle (EPUB), dịu mắt, cho người có nhiều sách PDF (ưu tiên tiếng Việt). **Lõi trung tính về lĩnh vực.**
- **Biến thể**: mỗi lĩnh vực là một biến thể (nội dung + tính năng bật bằng flag). Biến thể đầu tiên (để dogfood): **Đông y** — xem [`docs/variants/dongy.md`](./docs/variants/dongy.md).
- **Người dùng**: hiện tại là chính tác giả (dogfooding). Thương mại hóa (vd bán cho sinh viên Đông y) là hướng của **riêng biến thể Đông y**, không phải lõi.
- **Giai đoạn hiện tại**: **THIẾT KẾ** → sắp sang **implementation**. Tài liệu trong `docs/` là nguồn chân lý; đọc trước khi code.

## Quyết định đã chốt (mỗi dòng → ADR)

- **Nền tảng**: Kotlin Multiplatform + Compose Multiplatform, **Android trước**, iOS sau cùng codebase.
- **Bộ hiển thị EPUB**: foliate-js trong WebView (`compose-webview-multiplatform`), **không** Readium lúc đầu — [ADR-001](./docs/05-tech-decisions.md#adr-001--bộ-hiển-thị-epub-foliate-js-trong-webview-không-readium-lúc-đầu). Tự cấu hình WebViewAssetLoader (Android) / WKURLSchemeHandler (iOS) để tránh CORS `file://`.
- **Database**: SQLDelight (Room là lựa chọn thay thế) — [ADR-002](./docs/05-tech-decisions.md).
- **DI**: Koin — [ADR-003](./docs/05-tech-decisions.md).
- **Pipeline PDF→EPUB**: chạy bằng **Python trên máy tính** (không trên điện thoại); PyMuPDF mặc định & **bắt buộc cho font cũ**, Docling cho sách Unicode phức tạp, dựng EPUB bằng ebooklib — [ADR-004](./docs/05-tech-decisions.md), [ADR-005](./docs/05-tech-decisions.md).
- **License AGPL**: PyMuPDF/ebooklib là AGPL → pipeline **tách rời app**, app KMP **không link** AGPL — [ADR-004](./docs/05-tech-decisions.md), [R-08](./docs/06-risks.md).
- **Cấu hình biến thể**: object `VariantConfig` (gồm **tên app + màu thương hiệu**, **danh sách font fallback theo hệ chữ**, map feature flags, trỏ tới content pack); **chưa** dùng Gradle flavors/Xcode targets — [ADR-007](./docs/05-tech-decisions.md).
- **Định danh sách ổn định**: pipeline ghi `dc:identifier` cố định (`sepia:` + SHA-256 PDF gốc) → `Book.bookUid`, không đổi giữa các lần build; nhập bản build lại → thay file + re-anchor, không tạo cuốn trùng — [04-data-model.md §6](./docs/04-data-model.md).
- **Re-anchor chạy trong JS** bằng `search` của foliate-js (có dự phòng tìm `textSnippet` + xác nhận `prefix`/`suffix`), không parser EPUB phía Kotlin — [ADR-008](./docs/05-tech-decisions.md).
- **Highlight mồ côi không bị xóa**: re-anchor thất bại → đánh dấu `orphan`, vẫn hiển thị và vẫn xuất Markdown — [04-data-model.md §3](./docs/04-data-model.md).

## Cấu trúc thư mục

```
sepia/
├── docs/              # 01..07: requirements, architecture, pipeline, data-model, ADRs, risks, roadmap
│   └── variants/      # biến thể theo lĩnh vực (dongy.md…) — nơi chứa mọi thứ đặc thù
├── pdf-pipeline/      # Python CLI (PDF → EPUB) — KHÔNG thuộc app KMP, license AGPL tách biệt
├── composeApp/        # thư viện KMP: commonMain (domain/data/reader/theme/overlay/annotation/feature/variant)
│                      #               androidMain / iosMain (actual tối thiểu) — AGP 9: library, KHÔNG phải app
├── androidApp/        # launcher Android mỏng (com.android.application) — MainActivity + manifest
├── iosApp/            # vỏ iOS SwiftUI nhúng framework ComposeApp (.xcodeproj tạo khi có Xcode)
├── gradle/            # libs.versions.toml (version catalog)
├── CLAUDE.md          # file này
└── README.md
```

## Nguyên tắc

- **Android trước**: dogfood ngay trên Android; iOS luôn **time-box** và **không chặn** việc dùng hằng ngày.
- **Mỗi mốc ra một bản dùng được** (xem [07-roadmap.md](./docs/07-roadmap.md)); ưu tiên một lát dọc chạy được hơn làm xong một lớp.
- **Lõi trung tính về lĩnh vực (QUAN TRỌNG)**: code và docs **lõi KHÔNG chứa khái niệm thuộc lĩnh vực cụ thể** (vd huyệt, kinh lạc, Hán Việt…). Mọi thứ đặc thù đi vào `docs/variants/` hoặc lớp content/feature **bật bằng feature flag** trong `VariantConfig`.
- **Không xây "nền tảng cho mọi thứ"**: chỉ giữ ranh giới 3 lớp (lõi / nội dung / biến thể) đủ sạch để tách sau.
- **Ghi chú luôn xuất được ra ngoài**: Markdown + xuất file DB; highlight không định vị được → đánh dấu "orphan", **không xóa** ([04-data-model.md](./docs/04-data-model.md) §3).
- **Không gửi dữ liệu ra mạng**: offline-first, không tài khoản, không telemetry (NFR-2, NFR-6).
- **Giải pháp đơn giản, ít phụ thuộc, dễ bảo trì một người** (NFR-4).

## KHÔNG làm ở giai đoạn này

- Không viết code app/pipeline khi đang ở bước duyệt thiết kế (trừ khi được yêu cầu).
- Không lên store, không tài khoản/thanh toán/DRM, không cloud sync.
- Không OCR (trừ khi SPIKE-0 cho thấy kho PDF chủ yếu là scan — [R-11](./docs/06-risks.md)).
- Không làm tính năng tra cứu/từ điển đặc thù lĩnh vực, gom ghi chú theo nhãn/chủ đề, hay xem PDF gốc trong app (nhóm US-F — giai đoạn sau; phần đặc thù thuộc `docs/variants/`).
- Không dùng Gradle flavors/Xcode targets; chưa tách Gradle module.
- Không làm độ ấm/độ sáng trong WebView (dùng lớp phủ Compose — xem 02 §8).

## Mốc hiện tại & việc kế tiếp

- **Hiện tại**: **Mốc 0 xong phần nền tảng** — `pdf-pipeline/` (uv + PyMuPDF 1.27.x, bước `detect` + test) và **app Android** (khung KMP + Compose MP, build xanh, đã chạy trên emulator: màn hình mở đầu "Sepia"). *(IDE cần Android Studio 2026 ≥ Rabbit để sync AGP 9.)*
- **Việc kế tiếp**: sang **Mốc 1** (pipeline ra EPUB sạch, đọc bằng KOReader). Còn **SPIKE-0** (chạy `detect` trên `samples/` → quyết định OCR) trong Mốc 0.
- **Việc riêng đang mở**: **iOS shell** (SPIKE-2 phần iOS) — chưa build iOS lần nào, chưa có `.xcodeproj` (chưa cài Xcode) → **[issue #3](https://github.com/trinhvandat/sepia/issues/3)**, xem `iosApp/README.md`. Xem [07-roadmap.md](./docs/07-roadmap.md).
