package io.github.trinhvandat.sepia.reader

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

/**
 * WebView chứa foliate-js. Android: compose-webview-multiplatform + WebViewAssetLoader.
 * iOS: hoãn (issue #3). [currentBookPath] = đường dẫn file EPUB đang mở (handler phục vụ qua https).
 */
@Composable
expect fun ReaderSurface(
    controller: ReaderController,
    currentBookPath: String?,
    modifier: Modifier,
)
