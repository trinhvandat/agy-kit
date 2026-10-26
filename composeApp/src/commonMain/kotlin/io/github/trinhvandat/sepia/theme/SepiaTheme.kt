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

    // --- Hằng typography (một nguồn chân lý; không rải trong ReaderScreen) ---
    // Thân bài ~1.2rem (≈19–20px trên điện thoại ở 100%), giãn dòng rộng, lề hai bên dễ chịu.
    const val BodyFontRem = 1.2
    const val SideMarginRem = 1.1
    const val LineHeightBody = 1.6
    const val ParaSpacingEm = 0.9

    // Heading chỉ to hơn thân bài vừa phải, đậm vừa, giãn dòng khít hơn, KHÔNG ép viết hoa.
    const val LineHeightHeading = 1.3
    const val H1Em = 1.35
    const val H2Em = 1.2
    const val HSmallEm = 1.1 // h3–h6
    const val FigcaptionEm = 0.85

    /**
     * CSS tiêm vào từng tài liệu chương (foliate renderer.setStyles), **ghi đè CSS của sách**.
     * @param fontScalePercent cỡ chữ người dùng (100 = mặc định); đặt ở `html` nên mọi cỡ `rem`/`em`
     *   bên dưới co giãn theo. Đổi cỡ chữ chỉ là CSS (không đụng DOM) → CFI (vị trí đọc) giữ nguyên.
     * @param fontFallback danh sách font theo VariantConfig (tên có dấu cách → bọc nháy).
     */
    fun css(fontScalePercent: Int, fontFallback: List<String>): String {
        val family = fontFallback.joinToString(", ") { name ->
            if (name.any { it.isWhitespace() }) "\"$name\"" else name
        }
        return """
            :root { color-scheme: light; }
            html {
                background: $BackgroundHex !important;
                font-size: $fontScalePercent% !important;
                -webkit-text-size-adjust: 100%;
            }
            body {
                background: $BackgroundHex !important;
                color: $ForegroundHex !important;
                font-family: $family !important;
                font-size: ${BodyFontRem}rem !important;
                line-height: $LineHeightBody !important;
                text-align: justify;
                margin: 0 !important;
                padding: 0 ${SideMarginRem}rem !important;
                hyphens: none;
            }
            p, li, blockquote { line-height: $LineHeightBody !important; }
            p { margin: 0 0 ${ParaSpacingEm}em !important; text-align: justify; text-justify: inter-word; }
            h1, h2, h3, h4, h5, h6 {
                line-height: $LineHeightHeading !important;
                font-weight: 600 !important;
                margin: 1.1em 0 0.5em !important;
                text-transform: none !important;
            }
            h1 { font-size: ${H1Em}em !important; }
            h2 { font-size: ${H2Em}em !important; }
            h3, h4, h5, h6 { font-size: ${HSmallEm}em !important; }
            figure { margin: 1em 0 !important; }
            img { max-width: 100% !important; height: auto !important; filter: sepia(0.06); }
            figcaption {
                font-size: ${FigcaptionEm}em !important;
                font-style: italic !important;
                opacity: 0.8;
                text-align: center;
            }
            a, a:visited { color: $ForegroundHex !important; }
        """.trimIndent()
    }

    const val MinFontScale = 80
    const val MaxFontScale = 200
    const val FontScaleStep = 10
    const val DefaultFontScale = 100
}
