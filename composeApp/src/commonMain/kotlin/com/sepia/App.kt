package com.sepia

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

/** Điểm vào UI dùng chung (commonMain). Baseline tối giản — sẽ thay ở bước màn hình mở đầu. */
@Composable
fun App() {
    MaterialTheme {
        Text("Sepia")
    }
}
