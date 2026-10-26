package io.github.trinhvandat.sepia.theme

/**
 * Theme Sepia (docs/01, 02 §2): màu chữ/nền qua CSS injection vào WebView (foliate renderer.setStyles).
 * Độ ấm/độ sáng KHÔNG ở đây (lớp phủ Compose — Mốc 4, §8). Font do app chèn theo VariantConfig.
 * Mốc 4 sẽ đủ 5 theme + @font-face; Mốc 2 chỉ Sepia + cỡ chữ cơ bản.
 */
object SepiaTheme {
    const val BackgroundArgb: Long = 0xFFF2E7D0 // nền giấy ngả vàng
    const val ForegroundArgb: Long = 0xFF5B4636 // nâu chữ

    const val BackgroundHex = "#F2E7D0"
    const val ForegroundHex = "#5B4636"

    /**
     * CSS tiêm vào từng tài liệu chương (foliate renderer.setStyles).
     * @param fontScalePercent cỡ chữ (100 = mặc định).
     * @param fontFallback danh sách font theo VariantConfig (tên có dấu cách → bọc nháy).
     */
    fun css(fontScalePercent: Int, fontFallback: List<String>): String {
        val family = fontFallback.joinToString(", ") { name ->
            if (name.any { it.isWhitespace() }) "\"$name\"" else name
        }
        return """
            :root { color-scheme: light; }
            html { background: $BackgroundHex !important; }
            body {
                background: $BackgroundHex !important;
                color: $ForegroundHex !important;
                font-family: $family !important;
                font-size: $fontScalePercent% !important;
                line-height: 1.6 !important;
            }
            p, li, blockquote { line-height: 1.6 !important; }
            p { text-align: justify; text-justify: inter-word; }
            a, a:visited { color: $ForegroundHex !important; }
            img { filter: sepia(0.06); }
        """.trimIndent()
    }

    const val MinFontScale = 70
    const val MaxFontScale = 220
    const val FontScaleStep = 10
    const val DefaultFontScale = 100
}
