package io.github.trinhvandat.sepia.feature

import androidx.compose.runtime.Composable

/**
 * Bắt nút **Back** của nền tảng (Android). iOS không có nút back hệ thống → no-op (vỏ iOS tự lo).
 * Tách expect/actual để commonMain không phụ thuộc artifact back-handler riêng.
 */
@Composable
expect fun ReaderBackHandler(enabled: Boolean, onBack: () -> Unit)
