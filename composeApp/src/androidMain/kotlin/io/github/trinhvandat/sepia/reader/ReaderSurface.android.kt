package io.github.trinhvandat.sepia.reader

import android.content.Context
import android.content.pm.ApplicationInfo
import android.view.ActionMode
import android.webkit.WebResourceResponse
import android.webkit.WebView as AndroidWebView
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
import com.multiplatform.webview.web.LoadingState
import com.multiplatform.webview.web.PlatformWebViewParams
import com.multiplatform.webview.web.WebView
import com.multiplatform.webview.web.WebViewNavigator
import com.multiplatform.webview.web.rememberWebViewNavigator
import com.multiplatform.webview.web.rememberWebViewState
import java.io.File
import java.io.FileInputStream

@Composable
actual fun ReaderSurface(
    controller: ReaderController,
    currentBookPath: String?,
    modifier: Modifier,
) {
    val context = LocalContext.current
    val bookPath = rememberUpdatedState(currentBookPath)
    // Debug build: bật chrome://inspect + bật đo perf lật trang trong bridge.js (tắt ở release).
    val debuggable = remember { (context.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE) != 0 }

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

    // Khi trang reader.html tải xong → yêu cầu bridge gửi lại bridgeReady (backup cho race, review #2).
    LaunchedEffect(state.loadingState) {
        if (state.loadingState is LoadingState.Finished) {
            if (debuggable) navigator.evaluateJavaScript("window.__sepiaPerf = true;")
            navigator.evaluateJavaScript("window.sepia && window.sepia.ping && window.sepia.ping();")
        }
    }

    // Đăng ký handler JS→Kotlin (một lần cho mỗi bridge). Parse thuần ở commonMain
    // ([ReaderEventParser]) để test được không cần WebView; payload hỏng → Failure, không văng.
    LaunchedEffect(jsBridge, controller) {
        for (method in BRIDGE_METHODS) {
            jsBridge.register(
                handler(method) { params ->
                    ReaderEventParser.parse(method, params)?.let { controller.emit(it) }
                },
            )
        }
        // Debug-only: đo perf lật trang (bridge.js post('perf', …)) → logcat tag "SepiaPerf". Tắt ở release.
        if (debuggable) jsBridge.register(handler("perf") { params -> android.util.Log.i("SepiaPerf", params) })
    }

    WebView(
        state = state,
        modifier = modifier,
        captureBackPresses = false,
        navigator = navigator,
        webViewJsBridge = jsBridge,
        onCreated = {
            // Debug build: bật chrome://inspect để soi console/network foliate-js.
            if (debuggable) AndroidWebView.setWebContentsDebuggingEnabled(true)
        },
        platformWebViewParams = PlatformWebViewParams(client = client),
        // Chặn ActionMode chọn chữ của hệ thống → thay bằng thanh Compose (Mốc 3a SPIKE).
        factory = { param -> NoSelectionMenuWebView(param.context) },
    )
}

/**
 * WebView chặn **ActionMode chọn chữ của hệ thống** (Sao chép/Chia sẻ/Tìm…) để không đè thanh
 * "Highlight" Compose của Mốc 3b. Vẫn GIỮ tay cầm chọn chữ — chỉ bỏ thanh công cụ nổi.
 */
private class NoSelectionMenuWebView(context: Context) : AndroidWebView(context) {
    override fun startActionMode(callback: ActionMode.Callback?): ActionMode? = null
    override fun startActionMode(callback: ActionMode.Callback?, type: Int): ActionMode? = null
}

/** Tên method JS→Kotlin cần đăng ký handler; parse ở [ReaderEventParser]. */
private val BRIDGE_METHODS = listOf(
    "bridgeReady", "ready", "relocated", "reanchorResult",
    "tap", "selection", "selectionCleared", "highlightTap", "error",
    "toc", "link",
)

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

