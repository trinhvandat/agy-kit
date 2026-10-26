package io.github.trinhvandat.sepia.feature

import androidx.compose.runtime.Composable

/** Ẩn thanh hệ thống khi đọc (docs/07 Mốc 2). Android: WindowInsetsController; iOS: hoãn. */
@Composable
expect fun ImmersiveReaderEffect(enabled: Boolean)
