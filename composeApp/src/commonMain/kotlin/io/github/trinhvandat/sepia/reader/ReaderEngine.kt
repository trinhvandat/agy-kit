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

/** Sự kiện từ WebView/foliate-js về Kotlin (JS→Kotlin qua kmpJsBridge). */
sealed interface ReaderEvent {
    data object BridgeReady : ReaderEvent
    data class Ready(val restoredCfi: String?) : ReaderEvent
    data class Relocated(
        val cfi: String,
        val fraction: Float,
        val snippet: String,
        val prefix: String,
        val suffix: String,
    ) : ReaderEvent
    data class ReanchorResult(val token: String, val cfis: List<String>) : ReaderEvent
    data class Failure(val where: String, val message: String) : ReaderEvent
}

/**
 * Bề mặt điều khiển reader (ADR-001: bọc foliate-js sau interface — UI không biết renderer).
 * Lệnh Kotlin→JS phát qua [evaluate] (do [ReaderSurface] nối với navigator.evaluateJavaScript).
 * Giới hạn bề mặt bridge đúng R-01: open/goTo/next/prev/applyStyle/reAnchor.
 */
class ReaderController {
    internal var evaluate: ((String) -> Unit)? = null

    private val _events = MutableSharedFlow<ReaderEvent>(replay = 0, extraBufferCapacity = 64)
    val events: SharedFlow<ReaderEvent> = _events.asSharedFlow()

    internal fun emit(event: ReaderEvent) { _events.tryEmit(event) }

    fun open(cacheKey: String, startCfi: String?) =
        eval("window.sepia.open(${js(ReaderUrls.bookUrl(cacheKey))}, ${jsOrNull(startCfi)})")

    fun goTo(cfi: String) = eval("window.sepia.goTo(${js(cfi)})")
    fun goToFraction(fraction: Float) = eval("window.sepia.goToFraction($fraction)")
    fun next() = eval("window.sepia.next()")
    fun prev() = eval("window.sepia.prev()")
    fun applyStyle(css: String) = eval("window.sepia.applyStyle(${js(css)})")

    fun reAnchor(token: String, fullQuery: String, snippetQuery: String, targetFraction: Float) =
        eval("window.sepia.reAnchor(${js(token)}, ${js(fullQuery)}, ${js(snippetQuery)}, $targetFraction)")

    private fun eval(script: String) { evaluate?.invoke(script) }

    private companion object {
        /** JSON-encode → literal chuỗi JS an toàn (nháy/newline/unicode). */
        fun js(s: String): String = Json.encodeToString(s)
        fun jsOrNull(s: String?): String = if (s == null) "null" else js(s)
    }
}
