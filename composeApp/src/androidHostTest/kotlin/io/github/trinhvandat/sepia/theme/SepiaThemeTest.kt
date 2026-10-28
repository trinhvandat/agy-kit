package io.github.trinhvandat.sepia.theme

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class SepiaThemeTest {
    private fun css(scale: Int = 100, fonts: List<String> = listOf("Noto Serif", "serif")) =
        SepiaTheme.css(scale, fonts)

    @Test
    fun rootScalesByPercentBodyIsLargerBase() {
        val c = css(scale = 120)
        // html mang cỡ gốc theo % người dùng; thân bài ~1.2rem (≈19–20px ở 100%).
        assertTrue(c.contains("font-size: 120%"), "có font-size % ở gốc")
        assertTrue(c.contains("1.2rem"), "thân bài dùng rem base")
        assertTrue(c.contains("line-height: 1.6"), "giãn dòng thân bài 1.6")
        assertTrue(c.contains("justify"), "căn đều hai bên")
    }

    @Test
    fun headingsModestAndNotForcedUppercase() {
        val c = css()
        assertTrue(c.contains("1.35em"), "h1 to vừa phải")
        assertTrue(c.contains("1.2em"), "h2 to vừa phải")
        assertTrue(c.contains("1.1em"), "h3–h6 to vừa phải")
        assertTrue(c.contains("line-height: 1.3"), "heading giãn dòng 1.3")
        assertFalse(c.contains("text-transform: uppercase"), "không ép viết hoa")
    }

    @Test
    fun imagesFitAndFigcaptionSmallerItalic() {
        val c = css()
        assertTrue(c.contains("max-width: 100%"), "ảnh co vừa khung")
        assertTrue(c.contains("height: auto"), "giữ tỷ lệ ảnh")
        assertTrue(c.contains("figcaption"), "có figcaption")
        assertTrue(c.contains("font-style: italic"), "figcaption nghiêng")
    }

    @Test
    fun tablesFitColumnWidthAndWrap() {
        val c = css()
        // Bảng nhiều cột KHÔNG tràn ngang / cắt cột: co vừa bề rộng cột + ngắt từ dài.
        assertTrue(c.contains("table-layout: fixed"), "bảng co cứng theo cột")
        assertTrue(c.contains("width: 100%"), "bảng rộng đúng cột")
        assertTrue(c.contains("word-break"), "ô bảng ngắt từ dài")
        assertTrue(c.contains("table"), "có quy tắc table")
    }

    @Test
    fun wideTablesBecomeCardsOnNarrowScreen() {
        val c = css()
        // Việc 4: bảng rộng (class "wide") → dạng "thẻ" trên màn hẹp; mỗi ô kèm nhãn cột.
        assertTrue(c.contains("@media (max-width: 560px)"), "có media query màn hẹp")
        assertTrue(c.contains("table.wide"), "nhắm bảng rộng class wide")
        assertTrue(
            c.contains("content: attr(data-label)"),
            "ô hiện nhãn cột từ data-label",
        )
        assertTrue(c.contains("break-inside: avoid"), "không cắt hàng qua trang")
    }

    @Test
    fun multiWordFontFamilyQuoted() {
        assertTrue(css().contains("\"Noto Serif\""), "font nhiều từ phải bọc nháy")
    }

    @Test
    fun fontScaleBoundsAndStep() {
        assertEquals(80, SepiaTheme.MinFontScale)
        assertEquals(200, SepiaTheme.MaxFontScale)
        assertEquals(10, SepiaTheme.FontScaleStep)
        assertEquals(100, SepiaTheme.DefaultFontScale)
    }
}
