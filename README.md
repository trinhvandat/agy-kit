# Sepia

**Sepia** là app đọc sách kiểu Kindle (EPUB reflow) với giao diện dịu mắt như sách giấy, dành cho người học **Đông y** có nhiều sách PDF. Kèm một pipeline Python chuyển PDF → EPUB sạch (xử lý cả font cũ TCVN3/VNI).

Làm trên **Kotlin Multiplatform + Compose Multiplatform** (Android trước, iOS sau), offline, không tài khoản — dùng hằng ngày và cải tiến dần (dogfooding).

Dự án đang ở **giai đoạn thiết kế**. Tài liệu thiết kế đầy đủ nằm trong [`docs/`](./docs/) (yêu cầu, kiến trúc, pipeline PDF, data model, ADR, rủi ro, roadmap). Hướng dẫn làm việc & các quyết định đã chốt xem [`CLAUDE.md`](./CLAUDE.md).
