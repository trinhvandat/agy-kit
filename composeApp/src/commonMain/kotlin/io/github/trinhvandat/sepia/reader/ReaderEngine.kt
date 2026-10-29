package io.github.trinhvandat.sepia.reader

import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

/**
 * URL phục vụ qua WebViewAssetLoader (origin `https` thay cho `file://` → tránh CORS — ADR-001).
 * `assets/reader/…` → asset app; `books/book.epub` → file EPUB hiện hành (handler nền tảng).
 */
object ReaderUrls {
    const val DOMAIN = "appassets.androidplatform.net"
    const val READER_HTML = "https://appassets.androidplatform.net/assets/reader/reader.html"
    const val ASSETS_PREFIX = "/assets/"
    const val BOOKS_PREFIX = "/books/"

    /** URL EPUB cố định; đổi `v` theo contentHash để bỏ cache khi mở cuốn khác/bản build khác. */
    fun bookUrl(cacheKey: String): String =
        "https://appassets.androidplatform.net/books/book.epub?v=$cacheKey"
}

/** Vùng chạm trên trang hiển thị (foliate báo theo tỉ lệ 30/40/30 — xem bridge.js). */
enum class TapZone { LEFT, CENTER, RIGHT }

/** Hình chữ nhật vùng chọn theo toạ độ TRANG CHỦ (CSS px), để đặt thanh nổi cạnh vùng chọn (Mốc 3b). */
data class SelectionRect(val x: Float, val y: Float, val w: Float, val h: Float)

/** Sự kiện từ WebView/foliate-js về Kotlin (JS→Kotlin qua kmpJsBridge). */
sealed interface ReaderEvent {
    data object BridgeReady : ReaderEvent
    data class Ready(val restoredCfi: String?, val cfiFailed: Boolean = false) : ReaderEvent
    data class Relocated(
        val cfi: String,
        val fraction: Float,
        val snippet: String,
        val prefix: String,
        val suffix: String,
        /** Mục lục đang đọc (từ `lastLocation.tocItem`) — để tô + cuộn tới trong bảng mục lục. */
        val tocLabel: String = "",
        val tocHref: String = "",
    ) : ReaderEvent
    data class ReanchorResult(
        val token: String,
        val candidates: List<io.github.trinhvandat.sepia.domain.AnchorCandidate>,
    ) : ReaderEvent

    /** Chạm đơn trong WebView (không phải link/không đang chọn chữ) — Kotlin quyết hành động UI. */
    data class Tap(val zone: TapZone) : ReaderEvent

    /** Vùng chọn chữ không rỗng — kèm CFI range + neo (prefix/suffix) + fraction để dựng Highlight (3b). */
    data class Selection(
        val cfi: String,
        val text: String,
        val prefix: String,
        val suffix: String,
        val fraction: Float,
        val rect: SelectionRect,
    ) : ReaderEvent

    /** Vùng chọn bị xoá (chạm ra ngoài, lật trang…). */
    data object SelectionCleared : ReaderEvent

    /** Chạm trúng một highlight đã vẽ → mở thanh đổi màu / sao chép / xoá (Mốc 3b). */
    data class HighlightTap(val id: String, val rect: SelectionRect) : ReaderEvent

    /** Mục lục cuốn sách (đáp lại `getToc`), dạng cây có cấp — để dựng bảng mục lục. */
    data class Toc(val items: List<TocItem>) : ReaderEvent

    /** Sắp theo một **link trong sách** — báo CFI hiện tại để Kotlin đẩy vào ngăn xếp "quay lại". */
    data class LinkJump(val fromCfi: String) : ReaderEvent

    data class Failure(val where: String, val message: String) : ReaderEvent
}

/** Một highlight cần vẽ (Kotlin→JS). color = mã CSS (HighlightColor.cssColor). */
@kotlinx.serialization.Serializable
data class HighlightDraw(val id: String, val cfi: String, val color: String)

/**
 * Bề mặt điều khiển reader (ADR-001: bọc foliate-js sau interface — UI không biết renderer).
 * Lệnh Kotlin→JS phát qua [evaluate] (do [ReaderSurface] nối với navigator.evaluateJavaScript).
 * Giới hạn bề mặt bridge đúng R-01: open/goTo/next/prev/applyStyle/reAnchor/clearSelection.
 */
class ReaderController {
    internal var evaluate: ((String) -> Unit)? = null

    private val _events = MutableSharedFlow<ReaderEvent>(replay = 0, extraBufferCapacity = 64)
    val events: SharedFlow<ReaderEvent> = _events.asSharedFlow()

    internal fun emit(event: ReaderEvent) { _events.tryEmit(event) }

    fun open(cacheKey: String, startCfi: String?) =
        eval("window.sepia.open(${js(ReaderUrls.bookUrl(cacheKey))}, ${jsOrNull(startCfi)})")

    fun goTo(cfi: String) = eval("window.sepia.goTo(${js(cfi)})")
    fun goToHref(href: String) = eval("window.sepia.goToHref(${js(href)})")
    fun goToStart() = eval("window.sepia.goToStart()")
    fun goToFraction(fraction: Float) = eval("window.sepia.goToFraction($fraction)")

    /** Yêu cầu JS gửi lại mục lục (phát ReaderEvent.Toc). */
    fun requestToc() = eval("window.sepia.getToc()")

    // Lật trang qua CHẠM nay xử lý thẳng trong JS (bridge.js onDocClick) cho mượt — KHÔNG đi qua đây.
    // next()/prev() giữ cho lật bằng lệnh (vd phím/điều khiển ngoài sau này), không gọi khi nhận Tap.
    fun next() = eval("window.sepia.next()")
    fun prev() = eval("window.sepia.prev()")
    fun applyStyle(css: String) = eval("window.sepia.applyStyle(${js(css)})")

    /** Bật/tắt hiệu ứng trượt lật trang (Trượt/Không). */
    fun setPageAnimation(enabled: Boolean) = eval("window.sepia.setPageAnimation($enabled)")

    fun clearSelection() = eval("window.sepia.clearSelection()")

    /** Thay toàn bộ tập highlight đang vẽ. */
    fun setHighlights(items: List<HighlightDraw>) =
        eval("window.sepia.setHighlights(${Json.encodeToString(items)})")

    fun removeHighlight(id: String) = eval("window.sepia.removeHighlight(${js(id)})")

    fun reAnchor(token: String, fullQuery: String, snippetQuery: String, targetFraction: Float) =
        eval("window.sepia.reAnchor(${js(token)}, ${js(fullQuery)}, ${js(snippetQuery)}, $targetFraction)")

    private fun eval(script: String) { evaluate?.invoke(script) }

    private companion object {
        /** JSON-encode → literal chuỗi JS an toàn (nháy/newline/unicode). */
        fun js(s: String): String = Json.encodeToString(s)
        fun jsOrNull(s: String?): String = if (s == null) "null" else js(s)
    }
}
