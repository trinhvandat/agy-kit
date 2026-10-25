# Sepia

**Sepia** là **bản nền (lõi)** cho app đọc sách **reflow** kiểu Kindle, giao diện dịu mắt như sách giấy, dành cho người có nhiều sách PDF (ưu tiên sách tiếng Việt). Kèm một pipeline Python chuyển PDF → EPUB sạch (xử lý cả font cũ TCVN3/VNI — vấn đề chung của PDF tiếng Việt đời cũ).

Lõi **trung tính về lĩnh vực**: mỗi lĩnh vực là một **biến thể** riêng (gói nội dung + tính năng bật bằng feature flag), không nằm trong lõi. Biến thể đầu tiên — dùng để dogfood — là **Đông y** (xem [`docs/variants/dongy.md`](./docs/variants/dongy.md)).

Làm trên **Kotlin Multiplatform + Compose Multiplatform** (Android trước, iOS sau), offline, không tài khoản — dùng hằng ngày và cải tiến dần (dogfooding).

Dự án đang ở **giai đoạn thiết kế**. Tài liệu thiết kế đầy đủ nằm trong [`docs/`](./docs/) (yêu cầu, kiến trúc, pipeline PDF, data model, ADR, rủi ro, roadmap) và các biến thể trong [`docs/variants/`](./docs/variants/). Hướng dẫn làm việc & các quyết định đã chốt xem [`CLAUDE.md`](./CLAUDE.md).
