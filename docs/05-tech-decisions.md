# 05 — Quyết định kỹ thuật (ADRs)

> Dạng ADR: **Bối cảnh → Phương án → Ưu/nhược → Quyết định**.
> Phiên bản **kiểm tra bằng web 2026-10-25** (không dựa trí nhớ). Nguồn ở cuối file.
> Cập nhật: 2026-10-26.

## Bảng phiên bản chốt (version catalog)

| Thành phần | Phiên bản | Ghi chú |
|------------|-----------|---------|
| Kotlin | **2.4.20** | 2.x hiện hành; language release 2.4.0 (6/2026) |
| Compose Multiplatform | **1.12.2** | iOS **Stable** (từ 1.8.0, 5/2025); không cần tự align Kotlin |
| SQLDelight | **2.3.2** | KMP first-class, SQL type-safe compile-time |
| Room (androidx.room) | **2.8.5** | KMP stable (thay thế); Room 3.0 còn **alpha** |
| Koin | **4.2.1** | KMP + compile-safe (Koin Compiler) |
| kotlinx.coroutines | **1.11.0** | |
| kotlinx.serialization | **1.9.0** | cần Kotlin 2.2+ |
| kotlinx-datetime | **0.8.0** | vẫn pre-1.0; có thể pin 0.7.1 nếu cần chắc |
| compose-webview-multiplatform | **2.0.3** | Android + iOS (WKWebView) + Desktop; có JS bridge + raw WebView access |
| foliate-js | *không semver* | **vendor theo git submodule, pin SHA**; MIT |
| foliate-kmp-core | **0.1.0-beta01** | **CHỈ tham khảo cách bắc cầu — KHÔNG dùng làm dependency** (C5) |
| Readium kotlin-toolkit | **3.4.0** | (phương án dự phòng) |
| Readium swift-toolkit | **3.11.0** | (phương án dự phòng) |

---

## ADR-001 — Bộ hiển thị EPUB: **foliate-js trong WebView** (không Readium, lúc đầu)

**Bối cảnh**: cần renderer EPUB reflow trên cả Android + iOS; người làm một mình, ~10h/tuần, **chưa từng build iOS**; cần CFI để neo highlight; sách không DRM.

**Phương án**:
- **A. foliate-js trong WebView** (qua `compose-webview-multiplatform` 2.0.3).
- **B. Readium** (kotlin-toolkit 3.4.0 + swift-toolkit 3.11.0).

**Ưu/nhược**:

| | foliate-js + WebView (A) | Readium (B) |
|---|--------------------------|-------------|
| Chia sẻ code | ★ **Một renderer** cho cả 2 OS (JS + 1 bridge) | ✗ **Hai toolkit native** (Kotlin + Swift), không có lớp KMP/Compose chung → tích hợp 2 lần |
| Hợp người chưa biết iOS | ★ Không cần viết Swift đáng kể | ✗ Phải tích hợp swift-toolkit bằng Swift |
| Theme/cỡ chữ/lề | ★ CSS injection — tự nhiên | Trung bình (API navigator) |
| CFI / highlight | Có CFI parser + overlay SVG | Có Locator (chứa CFI) + Decorations API |
| Độ chín / ổn định API | ✗ foliate-js **tự nhận "không ổn định"** | ★ Battle-tested |
| Công sức bridge | ✗ Tự viết JS↔Kotlin | Ít hơn ở từng OS, nhưng nhân đôi |
| License | MIT | BSD-3 (LCP/DRM tính phí riêng — ta không cần) |

**Kết quả kiểm tra `compose-webview-multiplatform` (B3 — tra GitHub/source, không đoán):**
- ✅ **JS bridge hai chiều** có sẵn (`kmpJsBridge`: JS→Kotlin `callNative`+`onCallback`; Kotlin→JS `evaluateJavaScript` nhận kết quả qua callback). Rất hợp để bắc cầu foliate-js (`goTo(cfi)`, `currentCfi`, selection range, highlight). Lưu ý: **chỉ async**, dữ liệu trả về là String/JSON (tự serialize).
- ✅ **Truy cập raw WebView** qua `onCreated(NativeWebView)` (Android `WebView` / iOS `WKWebView`) + có `RequestInterceptor`/`WebSettings` → **tự cấu hình được** asset loader.
- ✅ Nạp HTML/file local + inline HTML có `baseUrl`.
- ⚠️ **KHÔNG** tích hợp sẵn `WebViewAssetLoader` (Android) hay `WKURLSchemeHandler` (iOS); mặc định dùng `file://` (Android `file:///android_asset`, iOS `loadFileURL`). → foliate-js dùng fetch/Blob **dễ dính chặn CORS `file://`**.
- ⚠️ iOS: đăng ký `WKURLSchemeHandler` phải làm **trước khi tạo WKWebView**, mà `onCreated` chạy **sau khi tạo** → có thể phải **tùy biến factory/fork** → **rủi ro spike**.
- ⚠️ Truyền **EPUB lớn**: không có API truyền bytes hạng nhất. foliate-js **tự giải nén zip trong JS**, nên hướng sạch nhất là **phục vụ chính file `.epub` qua asset loader/scheme handler local** (origin kiểu `https`) để foliate-js `fetch` được, tránh base64 qua bridge (issue #358 blob/download). Nếu range-request/zip trong WebView có vấn đề thì mới cân nhắc giải nén sẵn — **cần xác minh trong SPIKE-1**.
- ⚠️ iOS từng có issue render trắng khi nạp từ file (#230) → **phải test cả 2 OS**. (Desktop CEF nạp external resource đang hỏng #388 — ta không nhắm Desktop nên bỏ qua.)

**Quyết định**: **Chọn A (foliate-js + WebView)** cho giai đoạn đầu.
Lý do: tối đa hóa chia sẻ code và né viết Swift/tích hợp 2 toolkit — phù hợp người chưa build iOS, thời gian hẹp. Bridge + raw WebView access đã có sẵn.
**Việc phải tự làm (ghi rõ, B3)**: tự cấu hình **`WebViewAssetLoader` (Android)** và **`WKURLSchemeHandler` (iOS)** qua raw WebView để phục vụ EPUB + asset + font local qua scheme kiểu `https` (tránh CORS `file://`). Đây là phần native bắt buộc, không có sẵn trong thư viện.
**Giảm thiểu**: vendor foliate-js **pin SHA**; bọc sau interface `ReaderEngine` trong domain để đổi sang Readium mà không sửa UI/data.
**Cửa quyết định (A1)**: chạy **SPIKE-1 trên Android trước**; phần kiểm tra **iOS được time-box (tối đa ~6 giờ)** và **không chặn** việc dùng app hằng ngày trên Android. Quyết định giữ A dựa trên **kết quả Android** cộng kết quả iOS trong khung giờ đã định (xem [06-risks.md](./06-risks.md) R-01, [07-roadmap.md](./07-roadmap.md)).
**Điểm lật ngược (fallback B)**: nếu CFI/chọn-văn-bản/asset-loading bất ổn nghiêm trọng (nhất là iOS) → chuyển Readium, chấp nhận viết native 2 lần.

---

## ADR-002 — Persistence: **SQLDelight** (ưu tiên), Room là lựa chọn thay thế

**Bối cảnh**: cần DB local, KMP (Android + iOS). Người làm **vững SQL/Java backend**.
**Phương án**: SQLDelight 2.3.2 vs Room KMP 2.8.5.
**Ưu/nhược**:
- **SQLDelight**: viết **SQL thật**, sinh code Kotlin type-safe lúc compile; KMP chín, nhẹ, ít "magic". Rất hợp tư duy SQL-first.
- **Room KMP**: quen với dev Android, annotation-based; Room 3.0 còn alpha nên tránh.
**Quyết định**: **SQLDelight 2.3.2** — khớp thế mạnh SQL của bạn, ít phụ thuộc ngầm. Giữ truy cập DB sau interface `Repository` để đổi được. *(Nếu bạn thích kiểu annotation/entity như JPA hơn, Room 2.8.5 cũng ổn — điểm cần bạn duyệt.)*

---

## ADR-003 — DI: **Koin 4.2.1**

**Bối cảnh**: cần DI chạy trên KMP.
**Quyết định**: **Koin 4.2.1** — KMP đầy đủ, nay **compile-safe** qua Koin Compiler; đơn giản, phù hợp một người. kotlin-inject mạnh hơn về kiểm tra compile nhưng dựng phức tạp — chưa cần.

---

## ADR-004 — Công cụ trích PDF: **PyMuPDF** mặc định & **bắt buộc cho font cũ**; Docling cho sách Unicode phức tạp

**Bối cảnh**: sách đủ loại (text + ảnh), có thể có font cũ; cần reading order/heading/bảng.
**Phương án**: PyMuPDF / Docling / Marker / Calibre (chi tiết [03-pdf-pipeline.md](./03-pdf-pipeline.md)).
**Quyết định**:
- **PyMuPDF 1.27.x** mặc định: trích chữ **theo span** (`get_text("dict")`) + detect + đọc tên font.
- **Ràng buộc (A5)**: sách/trang có **font cũ TCVN3/VNI BẮT BUỘC dùng PyMuPDF**, vì chuyển mã phải làm **theo từng span dựa trên tên font của span** — mà **Docling KHÔNG giữ font theo span** nên **không dùng được** cho loại này.
- **Docling 2.130 (MIT)** chỉ cho **sách Unicode** nhiều cột/bảng.
- **Marker 2.0** khi cần chất lượng cao/OCR (GPU; weights trả phí nếu doanh thu/vốn > $2M — cá nhân miễn phí).
- **Dựng EPUB bằng ebooklib** từ HTML sạch; **không** Calibre `ebook-convert` trực tiếp.
**Ràng buộc license (R-08)**: PyMuPDF + ebooklib là **AGPL**. Pipeline **tách rời app**, chỉ xuất `.epub`, app KMP **không link** AGPL. Nếu sau muốn pipeline thành dịch vụ phân phối → mua commercial PyMuPDF hoặc chuyển Docling (MIT).

---

## ADR-005 — Chuyển font cũ TCVN3/VNI: **port bảng chuyển, theo span, sau khi trích**

**Bối cảnh**: một số sách dùng TCVN3/VNI → rút ra là byte rác.
**Quyết định**: tự **port bảng chuyển đổi** vào Python (`legacy_encoding.py`) từ `vietnameseConverter` (R: TCVN3/VISCII/VPS) và **VietUnicode** (có VNI), chuẩn hóa NFC. Chạy **sau bước trích, theo từng span** (A5). Lý do: không có package Python chín phủ đủ (nhất là VNI). Làm **SPIKE-3** xác thực trước. Nhận diện font dùng regex có xử lý **tiền tố subset** + heuristic thống kê (B6).

---

## ADR-006 — Nơi lưu file & dữ liệu: **local, xuất chủ động, Markdown + DB**

**Bối cảnh**: NFR-3 (không mất ghi chú), NFR-6 (dữ liệu trên máy).
**Quyết định**: DB + file trong vùng app (transactional). Vì `filesDir` Android **không xem trực tiếp được**, sao lưu = **xuất chủ động ra ngoài** (share sheet / SAF): **xuất Markdown** và **xuất cả file DB** (B1). **Chưa** cloud sync. Chi tiết [04-data-model.md](./04-data-model.md) §5.

---

## ADR-007 — Tổ chức module & thương hiệu: **package + object BrandConfig; chưa dùng flavor/target**

**Bối cảnh**: cần ranh giới 3 lớp nhưng không over-engineer cho app một người dùng.
**Quyết định (C2)**:
- Phân lớp bằng **package** trong `composeApp`; chỉ tách Gradle module (`:core`, `:brand-*`) khi lõi ổn định và thực sự nhân bản app thứ hai.
- Thương hiệu/feature flags giai đoạn đầu **chỉ là một object `BrandConfig`** (tên app, màu mặc định, map flags). **Chưa** dùng **Gradle flavors / Xcode targets** — chỉ thêm khi làm app thứ hai.

---

## ADR-008 — Re-anchor chạy trong JS (foliate-js `search`), không parser EPUB phía Kotlin

**Bối cảnh (R2-3)**: khi EPUB build lại, phải định vị lại highlight **và vị trí đọc** từ `prefix+snippet+suffix` → cần duyệt nội dung sách và quy ra CFI.
**Phương án**:
- **A. Dùng `search` của foliate-js trong WebView**, gọi qua bridge `kmpJsBridge`.
- **B. Viết parser EPUB phía Kotlin** (giải nén zip + đọc XHTML + tự tính CFI).
**Ưu/nhược**: B lặp lại chính bộ máy đã có trong foliate-js (CFI + duyệt nội dung), thêm phụ thuộc và rủi ro lệch CFI giữa hai bộ máy; A tái dùng đúng engine đang render nên CFI nhất quán.
**Quyết định**: **Chọn A.** Kotlin chỉ lưu neo (snippet/prefix/suffix/contentHash/progress) và điều phối; WebView trả CFI mới. **Chuẩn hóa NFC + gộp khoảng trắng** ở cả chuỗi lưu lẫn nội dung sách trước khi so khớp (tránh trượt vì khác xuống dòng/thụt lề giữa các bản build). Phù hợp NFR-4 (ít phụ thuộc). Thêm vào **checklist SPIKE-1** ([06-risks.md](./06-risks.md) R-01). Chi tiết thuật toán: [04-data-model.md](./04-data-model.md) §3 & §3.1.

---

## Nguồn (kiểm tra 2026-10-25)
- Kotlin / Compose MP: kotlinlang.org/docs/releases.html; kotlinlang.org/docs/multiplatform/compose-compatibility-and-versioning.html
- Room KMP: developer.android.com/jetpack/androidx/releases/room; developer.android.com/kotlin/multiplatform/room
- SQLDelight: central.sonatype.com (app.cash.sqldelight)
- Koin: klibs.io/project/InsertKoinIO/koin
- coroutines/serialization/datetime: central.sonatype.com (org.jetbrains.kotlinx)
- foliate-js: github.com/johnfactotum/foliate-js; foliate-kmp-core: central.sonatype.com/artifact/io.github.asadullah012/foliate-kmp-core
- Readium: github.com/readium/kotlin-toolkit, github.com/readium/swift-toolkit; readium.org/mobile
- compose-webview-multiplatform: github.com/KevinnZou/compose-webview-multiplatform (README; AndroidWebView.kt, IOSWebView.kt, WebViewJsBridge.kt; issues #388/#230/#278/#358)
- PyMuPDF: pypi.org/project/PyMuPDF; Docling: github.com/docling-project/docling; Marker: github.com/datalab-to/marker; Calibre: calibre-ebook.com
- Vietnamese legacy: cran.r-project.org/web/packages/vietnameseConverter; vietunicode.sourceforge.net
