package com.sepia

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.sepia.variant.VariantConfig

/** Màu nền sepia dịu mắt (docs/01 phong cách sách giấy). */
private val BackgroundSepia = Color(0xFFF2E7D0)

/** Màn hình mở đầu: nền sepia, hiện tên app lấy từ VariantConfig. */
@Composable
fun App(variant: VariantConfig = VariantConfig.Default) {
    MaterialTheme {
        Box(
            modifier = Modifier.fillMaxSize().background(BackgroundSepia),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = variant.appName,
                color = Color(variant.brandColor),
                fontSize = 40.sp,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}
