package io.github.trinhvandat.sepia.reader

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier

// iOS hoãn (issue #3): WKWebView + WKURLSchemeHandler làm ở SPIKE-1 phần iOS (time-box 6h).
@Composable
actual fun ReaderSurface(
    controller: ReaderController,
    currentBookPath: String?,
    modifier: Modifier,
) {
    Box(modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Text("Trình đọc iOS chưa hỗ trợ (issue #3)")
    }
}
