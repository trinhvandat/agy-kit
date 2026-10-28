package io.github.trinhvandat.sepia.feature

import androidx.activity.compose.BackHandler
import androidx.compose.runtime.Composable

@Composable
actual fun ReaderBackHandler(enabled: Boolean, onBack: () -> Unit) {
    BackHandler(enabled = enabled, onBack = onBack)
}
