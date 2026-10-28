package io.github.trinhvandat.sepia.reader

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class TocFilterTest {
    private val tree = listOf(
        TocItem("Phần I — Tổng luận", "p1.xhtml", 1, listOf(
            TocItem("Giác hơi trị liệu", "p1.xhtml#a", 2),
            TocItem("Châm cứu cơ bản", "p1.xhtml#b", 2),
        )),
        TocItem("Phần II — Thực hành", "p2.xhtml", 1, listOf(
            TocItem("Day bấm huyệt", "p2.xhtml#c", 2),
        )),
    )

    @Test
    fun emptyQueryReturnsWholeTree() {
        assertEquals(tree, TocFilter.filter(tree, "   "))
    }

    @Test
    fun matchIgnoresDiacriticsAndCase() {
        // "giac hoi" (bỏ dấu, thường) khớp "Giác hơi trị liệu"
        val out = TocFilter.filter(tree, "giac hoi")
        assertEquals(1, out.size)
        assertEquals("Phần I — Tổng luận", out[0].label)
        assertEquals(1, out[0].children.size)
        assertEquals("Giác hơi trị liệu", out[0].children[0].label)
    }

    @Test
    fun parentKeptWhenChildMatchesButParentDoesNot() {
        val out = TocFilter.filter(tree, "day bam huyet")
        assertEquals(1, out.size)
        assertEquals("Phần II — Thực hành", out[0].label)
        assertEquals("Day bấm huyệt", out[0].children.single().label)
    }

    @Test
    fun matchedParentKeepsAllChildren() {
        // Gõ đúng nhãn cha → giữ nguyên cả cây con để còn điều hướng vào trong.
        val out = TocFilter.filter(tree, "tong luan")
        assertEquals(1, out.size)
        assertEquals(2, out[0].children.size)
    }

    @Test
    fun noMatchReturnsEmpty() {
        assertTrue(TocFilter.filter(tree, "xyz không có").isEmpty())
    }
}
