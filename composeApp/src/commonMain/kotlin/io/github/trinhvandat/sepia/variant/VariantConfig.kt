package io.github.trinhvandat.sepia.variant

/**
 * Lớp 3 — Variant Config (ADR-007): cấu hình biến thể dạng một object, CHƯA dùng Gradle flavors/
 * Xcode targets. Giữ trung tính framework (màu dạng ARGB Long, không import Compose).
 *
 * @property appName tên app hiển thị trong UI.
 * @property brandColor màu thương hiệu, ARGB 0xAARRGGBB.
 * @property fontFallback danh sách font fallback (app chèn qua CSS theo hệ chữ; pipeline chỉ ghi serif).
 * @property featureFlags bật/tắt tính năng đặc thù biến thể; lõi chỉ cung cấp chỗ cắm.
 */
data class VariantConfig(
    val appName: String,
    val brandColor: Long,
    val fontFallback: List<String>,
    val featureFlags: Map<String, Boolean>,
) {
    companion object {
        /** Biến thể mặc định = lõi trung tính (dùng để dogfood khung app). */
        val Default: VariantConfig = VariantConfig(
            appName = "Sepia",
            brandColor = 0xFF5B4636,
            fontFallback = listOf("Literata", "Noto Serif", "Noto Serif CJK TC", "Noto Serif CJK SC", "serif"),
            featureFlags = emptyMap(),
        )
    }
}
