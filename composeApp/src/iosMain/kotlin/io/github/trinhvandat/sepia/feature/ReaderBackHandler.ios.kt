package io.github.trinhvandat.sepia.feature

import androidx.compose.runtime.Composable

/** iOS không có nút back hệ thống trong WebView reader — no-op (vỏ SwiftUI tự điều hướng). */
@Composable
actual fun ReaderBackHandler(enabled: Boolean, onBack: () -> Unit) {}
