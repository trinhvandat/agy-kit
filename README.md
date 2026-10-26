# Sepia

**Sepia** là **bản nền (lõi)** cho app đọc sách **reflow** kiểu Kindle, giao diện dịu mắt như sách giấy, dành cho người có nhiều sách PDF (ưu tiên sách tiếng Việt). Kèm một pipeline Python chuyển PDF → EPUB sạch (xử lý cả font cũ TCVN3/VNI — vấn đề chung của PDF tiếng Việt đời cũ).

Lõi **trung tính về lĩnh vực**: mỗi lĩnh vực là một **biến thể** riêng (gói nội dung + tính năng bật bằng feature flag), không nằm trong lõi. Biến thể đầu tiên — dùng để dogfood — là **Đông y** (xem [`docs/variants/dongy.md`](./docs/variants/dongy.md)).

Làm trên **Kotlin Multiplatform + Compose Multiplatform** (Android trước, iOS sau), offline, không tài khoản — dùng hằng ngày và cải tiến dần (dogfooding).

Dự án đang ở **giai đoạn thiết kế**. Tài liệu thiết kế đầy đủ nằm trong [`docs/`](./docs/) (yêu cầu, kiến trúc, pipeline PDF, data model, ADR, rủi ro, roadmap) và các biến thể trong [`docs/variants/`](./docs/variants/). Hướng dẫn làm việc & các quyết định đã chốt xem [`CLAUDE.md`](./CLAUDE.md).

## Chạy app

Khung app KMP + Compose Multiplatform (Mốc 0 / SPIKE-2). Phiên bản chốt xem [`docs/05`](./docs/05-tech-decisions.md).

**Yêu cầu**: JDK 17+ (đã test JDK 21), Android SDK. Tạo `local.properties` ở gốc repo (file này **không commit**):

```properties
sdk.dir=/Users/<ban>/Library/Android/sdk
```

> `compileSdk 37` sẽ được AGP tự tải nếu thiếu (đã chấp nhận license SDK). Không cần `ANDROID_HOME`.

### Android (lát dọc chạy được)

```bash
# Build APK debug (module launcher :androidApp, phụ thuộc thư viện :composeApp)
./gradlew :androidApp:assembleDebug
# → APK: androidApp/build/outputs/apk/debug/androidApp-debug.apk

# Cài & mở trên emulator/thiết bị (cần adb trong PATH hoặc dùng đường dẫn đầy đủ)
adb install -r androidApp/build/outputs/apk/debug/androidApp-debug.apk
adb shell am start -n io.github.trinhvandat.sepia/.MainActivity
```

> Ghi chú: AGP 9 không cho `com.android.application` ở chung module với plugin KMP, nên `:composeApp` là **thư viện** KMP, còn `:androidApp` là **launcher** mỏng. Build app phải gọi `:androidApp:assembleDebug` (không phải `:composeApp`).

#### Nhập & đọc sách (Mốc 2)

1. Tạo EPUB bằng pipeline: `pdf-pipeline/` → `convert` (ví dụ ra `pdf-pipeline/out/dongy_docling.epub`).
2. Đẩy file vào máy/emulator: `adb push dongy_docling.epub /sdcard/Download/`.
3. Mở app → bấm **"Thêm sách"** → chọn file `.epub` (bộ chọn hệ thống, lọc `application/epub+zip`).
   App chép vào bộ nhớ riêng, đọc `dc:identifier`→`bookUid`, lưu vào thư viện.
4. Bấm vào sách để đọc: **chạm nửa trái/phải** để lật trang, **chạm giữa** để ẩn/hiện thanh trên
   (nút ‹ Thư viện, tên sách, %, A−/A+). Vị trí đọc tự lưu; mở lại đúng trang.
5. Nhập lại **bản EPUB build lại** (cùng `bookUid`) → giữ nguyên vị trí đọc và **định vị lại** (re-anchor).

> **Trạng thái Mốc 2 (2026-10-26)**: **ĐÃ kiểm trên emulator Android (API 36)** — nhập EPUB, foliate-js
> render tiếng Việt nền sepia, lật trang, nhớ vị trí qua mở lại. Cửa quyết định ADR-001 **đóng (giữ
> foliate-js)**. Chọn chữ/highlight: Mốc 3 (xem [docs/07](./docs/07-roadmap.md)). iOS: hoãn (issue #3).

### iOS

⏳ **Chưa dựng được**: máy phát triển hiện **chưa cài Xcode** (chỉ có Command Line Tools), mà Kotlin/Native iOS cần toolchain Xcode. Nguồn Swift (`iosApp/`) + `iosMain` đã có; còn thiếu `iosApp.xcodeproj`. Các bước khi đã cài Xcode: xem [`iosApp/README.md`](./iosApp/README.md).
