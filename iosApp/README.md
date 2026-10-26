# iosApp — vỏ iOS (SwiftUI) cho Sepia

Vỏ iOS nhúng Compose UI chung qua framework `ComposeApp` (Kotlin/Native) do `:composeApp` sinh ra.

## Trạng thái (Mốc 0 / SPIKE-2)

⚠️ **Chưa build/chạy được trên máy hiện tại** vì **chưa cài Xcode đầy đủ** (chỉ có Command Line Tools).
Kotlin/Native target iOS cần toolchain của Xcode để biên dịch & link framework, nên:

- Nguồn Swift (`iOSApp.swift`, `ContentView.swift`, `Info.plist`) đã có sẵn ở đây.
- **File dự án `iosApp.xcodeproj` CHƯA được tạo** — tạo bằng tay không có Xcode để xác minh sẽ không đáng tin,
  nên để lại cho bước có Xcode. Đây là phần iOS đang tồn đọng của SPIKE-2 (time-box, không chặn Android).

## Khi đã cài Xcode — cách dựng project

1. Cài **Xcode** (App Store) rồi `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`.
2. Build framework từ Gradle (kiểm tra toolchain Kotlin/Native iOS):
   ```bash
   ./gradlew :composeApp:linkDebugFrameworkIosSimulatorArm64
   ```
3. Tạo `iosApp.xcodeproj` (một trong hai cách):
   - Chạy lại **KMP wizard**/Android Studio (New Project > Kotlin Multiplatform) để sinh `iosApp.xcodeproj` chuẩn rồi copy vào đây; hoặc
   - Tạo project iOS App trong Xcode, thêm các file Swift ở trên, và cấu hình:
     - **Framework Search Paths** trỏ tới output `:composeApp` (hoặc dùng script `embedAndSignAppleFrameworkForXcode`).
     - Build phase chạy `./gradlew :composeApp:embedAndSignAppleFrameworkForXcode`.
     - Link framework `ComposeApp`.
4. Mở simulator và chạy scheme `iosApp` (hoặc `xcodebuild -scheme iosApp -destination 'generic/platform=iOS Simulator'`).

Khi làm được, cập nhật `README.md` gốc mục “Chạy app” và đánh dấu phần iOS của SPIKE-2 trong `docs/07-roadmap.md`.
