package io.github.trinhvandat.sepia.reader

import android.webkit.WebResourceResponse
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.webkit.WebViewAssetLoader
import com.multiplatform.webview.jsbridge.IJsMessageHandler
import com.multiplatform.webview.jsbridge.JsMessage
import com.multiplatform.webview.jsbridge.rememberWebViewJsBridge
import com.multiplatform.webview.web.AccompanistWebViewClient
import com.multiplatform.webview.web.PlatformWebViewParams
import com.multiplatform.webview.web.WebView
import com.multiplatform.webview.web.WebViewNavigator
import com.multiplatform.webview.web.rememberWebViewNavigator
import com.multiplatform.webview.web.rememberWebViewState
import kotlinx.serialization.json.Json
import java.io.File
import java.io.FileInputStream

private val bridgeJson = Json { ignoreUnknownKeys = true }

@Composable
actual fun ReaderSurface(
    controller: ReaderController,
    currentBookPath: String?,
    modifier: Modifier,
) {
    val context = LocalContext.current
    val bookPath = rememberUpdatedState(currentBookPath)

    // WebViewAssetLoader: /assets/ → asset app (foliate-js, reader.html, bridge.js);
    // /books/ → file EPUB hiện hành. Origin https → foliate-js fetch được, không dính CORS file://.
    val client = remember(context) {
        val loader = WebViewAssetLoader.Builder()
            .setDomain(ReaderUrls.DOMAIN)
            .addPathHandler(ReaderUrls.ASSETS_PREFIX, WebViewAssetLoader.AssetsPathHandler(context))
            .addPathHandler(ReaderUrls.BOOKS_PREFIX, BookPathHandler { bookPath.value })
            .build()
        AccompanistWebViewClient().apply { assetLoader = loader }
    }

    val state = rememberWebViewState(ReaderUrls.READER_HTML).apply {
        webSettings.isJavaScriptEnabled = true
        webSettings.androidWebSettings.domStorageEnabled = true
    }
    val navigator = rememberWebViewNavigator()
    val jsBridge = rememberWebViewJsBridge(navigator)

    // Nối lệnh Kotlin→JS với navigator.
    DisposableEffect(navigator, controller) {
        controller.evaluate = { script -> navigator.evaluateJavaScript(script) }
        onDispose { controller.evaluate = null }
    }

    // Đăng ký handler JS→Kotlin (một lần cho mỗi bridge).
    LaunchedEffect(jsBridge, controller) {
        jsBridge.register(handler("bridgeReady") { controller.emit(ReaderEvent.BridgeReady) })
        jsBridge.register(handler("ready") { p ->
            controller.emit(ReaderEvent.Ready(decode<ReadyDto>(p)?.restoredCfi?.ifEmpty { null }))
        })
        jsBridge.register(handler("relocated") { p ->
            decode<RelocatedDto>(p)?.let {
                controller.emit(
                    ReaderEvent.Relocated(it.cfi, it.fraction, it.snippet, it.prefix, it.suffix),
                )
            }
        })
        jsBridge.register(handler("reanchorResult") { p ->
            decode<ReanchorDto>(p)?.let { controller.emit(ReaderEvent.ReanchorResult(it.token, it.cfis)) }
        })
        jsBridge.register(handler("error") { p ->
            decode<ErrorDto>(p)?.let { controller.emit(ReaderEvent.Failure(it.where, it.message)) }
        })
    }

    WebView(
        state = state,
        modifier = modifier,
        captureBackPresses = false,
        navigator = navigator,
        webViewJsBridge = jsBridge,
        platformWebViewParams = PlatformWebViewParams(client = client),
    )
}

private inline fun <reified T> decode(params: String): T? =
    runCatching { bridgeJson.decodeFromString<T>(params) }.getOrNull()

private fun handler(name: String, onMsg: (String) -> Unit): IJsMessageHandler =
    object : IJsMessageHandler {
        override fun methodName(): String = name
        override fun handle(message: JsMessage, navigator: WebViewNavigator?, callback: (String) -> Unit) {
            onMsg(message.params)
        }
    }

/** Phục vụ file EPUB hiện hành cho mọi request dưới `/books/` (bỏ qua tên + query ?v=). */
private class BookPathHandler(private val provider: () -> String?) : WebViewAssetLoader.PathHandler {
    override fun handle(path: String): WebResourceResponse? {
        val p = provider() ?: return WebResourceResponse(null, null, 404, "No book", emptyMap(), null)
        val file = File(p)
        if (!file.exists()) return WebResourceResponse(null, null, 404, "Missing", emptyMap(), null)
        return runCatching {
            WebResourceResponse(
                "application/epub+zip",
                null,
                200,
                "OK",
                mapOf("Access-Control-Allow-Origin" to "*"),
                FileInputStream(file),
            )
        }.getOrNull()
    }
}

@kotlinx.serialization.Serializable
private data class ReadyDto(val restoredCfi: String = "")

@kotlinx.serialization.Serializable
private data class RelocatedDto(
    val cfi: String = "",
    val fraction: Float = 0f,
    val snippet: String = "",
    val prefix: String = "",
    val suffix: String = "",
)

@kotlinx.serialization.Serializable
private data class ReanchorDto(val token: String = "", val cfis: List<String> = emptyList())

@kotlinx.serialization.Serializable
private data class ErrorDto(val where: String = "", val message: String = "")
