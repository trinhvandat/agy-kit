package io.github.trinhvandat.sepia

import androidx.compose.ui.window.ComposeUIViewController

/** Entry iOS — iosApp (Swift) gọi hàm này để lấy UIViewController chứa Compose UI chung. */
fun MainViewController() = ComposeUIViewController { App() }
