# 02 — Kiến trúc (Architecture)

> Cập nhật: 2026-10-26. Số phiên bản xem [05-tech-decisions.md](./05-tech-decisions.md).

## 1. Nguyên tắc kiến trúc

Tách **3 lớp** để sau này nhân bản thành nhiều biến thể app, nhưng **KHÔNG xây "nền tảng cho mọi thứ"** ngay. Chỉ giữ ranh giới sạch để tách ra được:

1. **Reading Core (lõi đọc dùng chung)** — logic đọc sách, theme, highlight/note, data layer. **Trung tính về lĩnh vực**: không biết gì về một lĩnh vực cụ thể (vd Đông y).
2. **Content Pack (gói nội dung)** — sách + metadata, tách rời khỏi code. App không hardcode sách.
3. **Variant Config (cấu hình biến thể)** — tên app, **màu thương hiệu**, danh sách font fallback, bật/tắt tính năng (feature flags), trỏ tới content pack. **Giai đoạn đầu chỉ là một object `VariantConfig`** (Gradle flavors / Xcode targets **để sau** khi làm app thứ hai — xem ADR-007).

Tuân thủ **Clean Architecture** nhẹ (domain không phụ thuộc framework), nhưng không over-engineer cho app một người dùng.

## 2. Quyết định nền tảng cốt lõi (tóm tắt, chi tiết ở ADR)

- **KMP + Compose Multiplatform**, UI chung ở `commonMain`.
- **Bộ hiển thị EPUB**: **foliate-js chạy trong WebView** (qua `compose-webview-multiplatform`) — một renderer dùng chung cho cả Android + iOS. (Readium là phương án dự phòng — xem ADR-001.)
- **Theme màu chữ/nền**: CSS injection vào WebView. **Độ ấm / độ sáng**: **lớp phủ Compose phủ toàn app** (không trong WebView — xem §8).
- Lý do chọn WebView+foliate-js: **một đường render duy nhất** cho 2 nền tảng, tránh tích hợp 2 toolkit native và viết Swift khi bạn chưa từng build iOS.

## 3. Sơ đồ module (Mermaid)

```mermaid
graph TD
    subgraph Desktop["Máy tính (Python CLI) — ngoài app"]
        PP["pdf-pipeline<br/>(PDF → EPUB sạch)"]
    end

    subgraph App["App Sepia (KMP + Compose MP)"]
        subgraph Variant["Lớp 3: Variant Config"]
            BF["object VariantConfig<br/>(tên app, màu thương hiệu,<br/>font fallback, feature flags)"]
        end

        subgraph Core["Lớp 1: Reading Core (commonMain)"]
            UI["feature-reader (Compose UI)<br/>feature-library<br/>feature-notes"]
            OVL["warmth/brightness<br/>(lớp phủ Compose toàn app)"]
            RE["reader-engine<br/>(bridge WebView ↔ foliate-js,<br/>CFI, pagination)"]
            THM["theme-engine<br/>(5 theme màu → CSS)"]
            ANN["annotation-engine<br/>(highlight+note gộp, re-anchor, export MD)"]
            DOM["domain<br/>(models + use cases)"]
            DATA["data<br/>(repositories)"]
            DB[("local DB<br/>SQLDelight")]
        end

        subgraph Content["Lớp 2: Content Pack"]
            CP["books (.epub) + manifest.json<br/>(nạp từ file, không hardcode)"]
        end

        subgraph Platform["Platform (androidMain / iosMain)"]
            WV["WebView actual<br/>(Android WebView / WKWebView)<br/>+ asset loader local"]
            FS["File import/export actual<br/>(SAF / UIDocumentPicker / share)"]
        end
    end

    PP -->|xuất .epub| CP
    BF --> UI
    UI --> OVL
    UI --> RE
    UI --> THM
    UI --> ANN
    RE --> DOM
    ANN --> DOM
    DOM --> DATA
    DATA --> DB
    DATA --> CP
    RE -. expect/actual .-> WV
    DATA -. expect/actual .-> FS
```

## 4. Cấu trúc thư mục KMP (đề xuất)

```
sepia/
├── docs/                         # tài liệu thiết kế
├── pdf-pipeline/                 # Python CLI, KHÔNG thuộc app KMP
│   ├── pyproject.toml
│   ├── sepia_pipeline/
│   │   ├── __main__.py           # CLI mỏng (argparse): lệnh `detect` (Mốc 0)
│   │   ├── detect.py             # SPIKE-0 + phát hiện text/scan/font cũ (theo span)
│   │   ├── legacy_encoding.py    # TCVN3/VNI → Unicode (sau trích, theo span)
│   │   ├── extract.py            # PyMuPDF (bắt buộc cho font cũ) / Docling
│   │   ├── reflow.py             # ghép đoạn, bỏ header/footer (không de-hyphen)
│   │   ├── toc.py                # nhận diện tiêu đề → mục lục
│   │   ├── build_epub.py         # ebooklib + CSS font-family: serif (mặc định; app quyết định font thật)
│   │   └── quality.py            # kiểm tra nhẹ (ký tự rác, số đoạn…)
│   └── tests/
│
├── composeApp/                   # thư viện KMP (AGP 9: com.android.kotlin.multiplatform.library)
│   └── src/
│       ├── commonMain/           # ★ phần lớn code ở đây
│       │   └── kotlin/io/github/trinhvandat/sepia/
│       │       ├── domain/       # models, use cases (thuần Kotlin)
│       │       ├── data/         # repositories, DB, file access (interface)
│       │       ├── reader/       # reader-engine: bridge WebView↔foliate-js, CFI, re-anchor
│       │       ├── theme/        # theme-engine: 5 theme màu → CSS
│       │       ├── overlay/      # warmth/brightness: lớp phủ Compose
│       │       ├── annotation/   # highlight(+note), export Markdown
│       │       ├── feature/      # UI Compose: reader, library, notes
│       │       ├── variant/      # VariantConfig (Lớp 3) — ADR-007
│       │       └── App.kt        # màn hình mở đầu (Compose UI chung)
│       ├── androidMain/          # actual Android: WebView + WebViewAssetLoader, SAF (KHÔNG chứa launcher)
│       ├── iosMain/              # actual iOS: WKWebView + WKURLSchemeHandler, UIDocumentPicker; MainViewController
│       └── commonMain/composeResources/
│           └── foliate/          # foliate-js (vendored, pin SHA) + reader.html + bridge.js + CSS theme
│
├── androidApp/                   # launcher Android mỏng (com.android.application) — MainActivity + manifest
│   └── src/main/{kotlin,res,AndroidManifest.xml}
│
├── iosApp/                       # vỏ iOS SwiftUI nhúng framework ComposeApp (.xcodeproj tạo khi có Xcode)
│   └── iosApp/{iOSApp.swift,ContentView.swift,Info.plist}
│
├── CLAUDE.md                     # hướng dẫn cho AI/người làm
├── settings.gradle.kts           # include :composeApp, :androidApp
└── gradle/ (libs.versions.toml)  # version catalog tập trung
```

> **Ranh giới 3 lớp vẫn bằng package** trong `:composeApp`; chưa tách `:core`/`:variant-*` (hoãn tới app thứ hai).
> **AGP 9 buộc tách module launcher**: `com.android.application` không còn ở chung module với plugin KMP, nên có thêm `:androidApp` mỏng. Đây là ràng buộc công cụ, không phải tách lõi/biến thể — xem [05 ADR-007](./05-tech-decisions.md#adr-007--tổ-chức-module--biến-thể-package--object-variantconfig-chưa-dùng-flavortarget).

## 5. Luồng dữ liệu: PDF → EPUB → màn hình đọc

```mermaid
sequenceDiagram
    participant U as Bạn (máy tính)
    participant PY as pdf-pipeline (Python)
    participant FILE as File .epub
    participant APP as App (Kotlin)
    participant WV as WebView + foliate-js
    participant DB as Local DB

    U->>PY: chạy script với 1 file PDF
    PY->>PY: detect theo span (text/scan/font cũ)
    PY->>PY: trích chữ → chuyển TCVN3/VNI theo span → Unicode
    PY->>PY: reflow (ghép đoạn) + TOC
    PY->>PY: trang ảnh (hình/sơ đồ/bảng) → nhúng dạng image
    PY->>FILE: xuất .epub sạch (đọc thử bằng KOReader — nhánh Pipeline)
    U->>APP: nhập .epub (SAF/UIDocumentPicker) → copy vào app
    APP->>APP: đọc dc:identifier → bookUid; tính contentHash
    alt bookUid đã có (build lại cùng cuốn)
        APP->>DB: thay file, cập nhật contentHash/pipelineVersion
        APP->>WV: nạp sách + yêu cầu re-anchor (search prefix+snippet+suffix)
        WV->>APP: (bridge) CFI mới cho vị trí đọc + từng Highlight
        APP->>DB: cập nhật positionCfi + cfiRange; cái nào fail → status=orphan
    else bookUid mới
        APP->>DB: tạo Book mới (bookUid, metadata, filePath, contentHash, pipelineVersion)
    end
    U->>APP: mở sách
    APP->>WV: nạp foliate-js + .epub (qua asset loader local) + CSS theme
    WV->>APP: (bridge kmpJsBridge) báo vị trí hiện tại dạng CFI
    APP->>DB: cập nhật Book.positionCfi + positionSnippet/prefix/suffix + progress
    U->>WV: chọn đoạn → highlight / ghi chú
    WV->>APP: (bridge) trả CFI range + prefix/suffix của vùng chọn
    APP->>DB: lưu Highlight (cfiRange, textSnippet, prefix, suffix, contentHash)
    U->>APP: xuất ghi chú / sao lưu
    APP->>FILE: ghi .md (share/SAF) + xuất file DB
```

## 6. Cơ chế expect/actual (phần native tối thiểu)

| Chức năng | commonMain (expect) | androidMain (actual) | iosMain (actual) |
|-----------|---------------------|----------------------|-------------------|
| WebView hiển thị | `ReaderWebView` composable | Android `WebView` | `WKWebView` |
| **Nạp EPUB local vào WebView** | `ReaderContentServer` | **`WebViewAssetLoader`** phục vụ qua `https://appassets/...` (tránh CORS `file://`); cấu hình qua `onCreated` → raw WebView | **`WKURLSchemeHandler`** custom scheme (lưu ý phải đăng ký *trước* khi tạo WKWebView → có thể cần tùy biến factory — rủi ro spike) |
| **Nhập file EPUB** | `FilePicker.pickEpub()` | **SAF** `ACTION_OPEN_DOCUMENT` → copy vào `filesDir` | **`UIDocumentPicker`** → copy vào Documents |
| **Xuất Markdown** | `FileExporter.exportMarkdown()` | **SAF** `ACTION_CREATE_DOCUMENT` hoặc share sheet | **share sheet**; bật `UIFileSharingEnabled` + `LSSupportsOpeningDocumentsInPlace` để hiện trong app Files |
| **Xuất file DB (sao lưu)** | `FileExporter.exportDatabase()` | SAF / share | share sheet / Files |
| Đường dẫn lưu nội bộ | `AppPaths` | `Context.filesDir` *(người dùng không xem trực tiếp được)* | Documents |
| DB driver | (SQLDelight driver) | Android driver | Native driver |

> **Về nạp file local**: `compose-webview-multiplatform` **không** tích hợp sẵn `WebViewAssetLoader` (Android) hay `WKURLSchemeHandler` (iOS) — mặc định nạp qua `file://` nên foliate-js (dùng fetch/Blob) **dễ dính chặn CORS**. Thư viện **có** cho truy cập raw WebView qua callback `onCreated(NativeWebView)` và **có JS bridge hai chiều** (`kmpJsBridge`: `callNative`+`onCallback`, `evaluateJavaScript`) rất hợp để bắc cầu foliate-js. → Ta **tự cấu hình** asset loader/scheme handler qua raw WebView. Chi tiết & rủi ro: [05-tech-decisions.md](./05-tech-decisions.md) ADR-001, [06-risks.md](./06-risks.md) R-01. Mục tiêu NFR-5: giữ danh sách `actual` ngắn, ổn định.

> **Re-anchor chạy trong JS (ADR-008)**: việc định vị lại highlight/vị trí đọc khi EPUB build lại được làm **trong WebView** bằng `search` của foliate-js (gọi qua bridge), **không** viết parser EPUB phía Kotlin. Kotlin chỉ giữ neo (snippet/prefix/suffix) và điều phối. Chuẩn hóa **NFC + gộp khoảng trắng** trước khi so khớp. Xem [04-data-model.md](./04-data-model.md) §3.1.

> **Bề mặt bridge (SPIKE-1 + Mốc 3a/3b + điều hướng)** — giữ hẹp đúng R-01. **Kotlin→JS** (`window.sepia.*`): `open/goTo/goToHref/goToStart/goToFraction/next/prev/applyStyle/reAnchor/clearSelection/setHighlights/removeHighlight/getToc`. **JS→Kotlin** (`kmpJsBridge.callNative`): `bridgeReady · ready · relocated{cfi,fraction,snippet,prefix,suffix,tocLabel,tocHref} · reanchorResult · error · tap{zone} · selection{cfi,text,prefix,suffix,fraction,rect} · selectionCleared · highlightTap{id,rect} · toc{items:[{label,href,level,children}]} · link{cfi}`. Parse JS→Kotlin ở **commonMain** (`ReaderEventParser`, test được không cần WebView; payload hỏng → `Failure`, không văng).
>
> **Điều hướng (PR reader-navigation)**: **mục lục** (`getToc` dựng cây từ `view.book.toc` → `toc{items}`; bảng bottom-sheet: Về đầu sách / cây gập-mở / ô TÌM lọc bỏ dấu / tô + cuộn tới mục đang đọc theo `relocated.tocHref`), **thanh tiến độ** (Slider; kéo chỉ xem trước %, **thả** mới `goToFraction`), **ngăn xếp "quay lại"** (`ReaderBackStack` ở commonMain, có unit test): mỗi cú **nhảy** (link trong sách `link{cfi}` / mục lục / thanh tiến độ / Về đầu sách) đẩy CFI hiện tại vào ngăn xếp. Ba lối quay lại: **nút Back Android** (`ReaderBackHandler` expect/actual — tin cậy), **nút "↩" trên thanh trên** khi ngăn xếp còn (tin cậy), và **chip nổi "↩ Quay lại trang trước"** ở **mép dưới** khi ẩn thanh (~8s). Ngăn xếp còn thì quay lại, hết thì về thư viện. Link trong sách đi qua event `link` (foliate tự điều hướng, ta chỉ ghi vị trí cũ).
>
> **Giới hạn chạm overlay trên WebView (quan trọng)**: nội dung foliate nằm trong **iframe** (paginator dùng closed shadow DOM + iframe `sandbox`). Trên Android WebView (Chromium), iframe **giành mọi cú chạm trong vùng nội dung** — overlay Compose *hoặc* phần tử trang-chủ đặt ĐÈ lên nội dung iframe **không nhận được chạm** (dù `elementFromPoint` báo nó ở trên cùng), cú chạm "lọt" xuống link/iframe. Overlay chỉ nhận chạm ở **mép trên/dưới** (ngoài iframe) — nơi thanh trên và Slider hoạt động. Vì vậy điều khiển "quay lại" đặt ở **thanh trên** (nút ↩) và **mép dưới** (chip), KHÔNG đặt chip bấm được đè giữa trang; nút Back Android là lối chắc chắn nhất.
>
> **Highlight (Mốc 3b)**: `setHighlights([{id,cfi,color}])` thay TOÀN BỘ tập đang vẽ; JS dùng `view.addAnnotation({value:cfi})` + vẽ bằng `Overlayer.highlight` (màu) khi foliate phát `draw-annotation`, vẽ lại khi `create-overlay` (section mới nạp). Chạm highlight → `highlightTap`. **Neo vùng chọn** (sửa lỗi review 3a) tách ra `anchor.js` (ES module thuần, test bằng `node --test`, dùng chung fixture với test Kotlin `AnchorText`): prefix/suffix GIỮ khoảng trắng ranh giới để `fullQuery` khớp khi re-anchor. Bảng màu highlight (`HighlightColor`) ở **theme lõi** — trung tính lĩnh vực.
>
> **Cử chỉ (Mốc 3a)**: **vuốt** lật trang do **paginator.js** (vendor) tự xử lý; **tap** đơn được bridge quy về khung nhìn **trang chủ** (iframe rộng hơn màn hình theo số cột → cộng `frameElement.getBoundingClientRect()`), báo `zone` 30/40/30, Kotlin quyết hành động (trái=prev, giữa=toggle thanh, phải=next). **Không còn lớp chạm Compose phủ WebView** (gỡ nợ Mốc 2 — nó nuốt nhấn-giữ chọn chữ). Vùng chọn: WebView/paginator theo dõi (tự cuộn khi chọn vắt trang); bridge đọc + báo CFI (`view.getCFI`) + neo cross-node. Menu chọn chữ hệ thống (ActionMode) bị **chặn** (WebView con override `startActionMode`), thay bằng thanh Compose.

## 7. Ranh giới "dễ nhân bản" cụ thể

- **Reading Core không import** bất cứ khái niệm thuộc lĩnh vực cụ thể nào. Mọi thứ đặc thù lĩnh vực (gói sách, từ điển, bộ nhãn gợi ý, tính năng tra cứu) nằm **ngoài lõi**.
- **Điểm mở rộng (extension points)** — có hai loại, đều đi qua `VariantConfig`:
  1. **Nội dung riêng**: gói sách (content pack), từ điển/dữ liệu tra cứu → nạp từ file/resource của biến thể, lõi không hardcode.
  2. **Tính năng riêng**: màn hình/tra cứu đặc thù (vd US-F2) → đăng ký ở lớp content/feature và **bật bằng feature flag** trong `VariantConfig`; lõi chỉ cung cấp chỗ cắm (hook/slot), không chứa logic lĩnh vực.
  Ví dụ cụ thể của biến thể đầu tiên (Đông y): [variants/dongy.md](./variants/dongy.md).
- **Content Pack** = thư mục `.epub` + `manifest.json` (tiêu đề, tác giả, thứ tự). App đọc manifest, không hardcode.
- **Variant Config** = object `VariantConfig` (tên app, **màu thương hiệu**, **danh sách font fallback theo hệ chữ**, map feature flags, trỏ tới content pack). **Font do app chèn qua CSS vào WebView** theo danh sách fallback này; **pipeline chỉ ghi `font-family: serif`** (một nguồn quyết định font — xem [03-pdf-pipeline.md](./03-pdf-pipeline.md) §8). Giai đoạn đầu **chưa** dùng Gradle flavors/Xcode targets — chỉ thêm khi thực sự làm app thứ hai (ADR-007). Thêm app mới lúc đó = thêm flavor/target + content pack + bật flag, không sửa lõi.

## 8. Độ ấm & độ sáng: lớp phủ Compose

- Hiện thực bằng **một lớp phủ Compose** vẽ trên toàn bộ app (phía trên cả WebView), **không** can thiệp CSS trong WebView.
- **Độ ấm** = lớp phủ màu cam alpha thấp; **độ sáng** = lớp phủ tối alpha thấp.
- Lớp phủ phải **không chặn thao tác chạm** (dùng modifier cho phép sự kiện xuyên qua, ví dụ không đặt `pointerInput` nuốt sự kiện) để lật trang/chọn chữ trong WebView vẫn hoạt động.
- Lý do: tách khỏi renderer → độc lập với foliate-js, dễ chỉnh, đồng nhất trên cả 2 OS, không phụ thuộc quirk WebView.
