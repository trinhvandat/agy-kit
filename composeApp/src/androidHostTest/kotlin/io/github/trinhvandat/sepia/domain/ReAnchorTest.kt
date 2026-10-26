package io.github.trinhvandat.sepia.domain

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class ReAnchorTest {
    @Test
    fun normalizeCollapsesWhitespaceAndNfc() {
        // Dấu tổ hợp: 'a' + U+0301 → NFC "á"; nhiều khoảng trắng/newline → một space.
        val raw = "Cá   phê\n\tnóng"
        assertEquals("Cá phê nóng", AnchorText.normalize(raw))
    }

    @Test
    fun fullQueryConcatenatesPrefixSnippetSuffix() {
        val anchor = TextAnchor("cfi", "snippet", "pre ", " suf", "h", 0.1f)
        assertEquals("pre snippet suf", AnchorText.fullQuery(anchor))
    }

    @Test
    fun snippetQueryIsSnippetOnly() {
        val anchor = TextAnchor("cfi", "  chỉ   đoạn  ", "pre", "suf", "h", 0.1f)
        assertEquals("chỉ đoạn", AnchorText.snippetQuery(anchor))
    }

    @Test
    fun chooseNearestPicksClosestProgress() {
        val candidates = listOf(
            AnchorCandidate("cfiA", 0.10f),
            AnchorCandidate("cfiB", 0.48f),
            AnchorCandidate("cfiC", 0.90f),
        )
        assertEquals("cfiB", ReAnchorSelector.chooseNearest(candidates, target = 0.50f)?.cfi)
        assertEquals("cfiA", ReAnchorSelector.chooseNearest(candidates, target = 0.0f)?.cfi)
        assertNull(ReAnchorSelector.chooseNearest(emptyList(), 0.5f))
    }
}
