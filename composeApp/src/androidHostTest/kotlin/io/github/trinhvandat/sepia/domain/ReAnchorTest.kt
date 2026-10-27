package io.github.trinhvandat.sepia.domain

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

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

    // --- Việc 2: khớp GẦN ĐÚNG bỏ dấu (bước 3, docs/04 §3) -------------------

    @Test
    fun stripDiacriticsRemovesVietnameseTonesAndDstroke() {
        assertEquals("duoi mom gai dot", AnchorSimilarity.stripDiacritics("dưới mỏm gai đốt"))
        // Neo ABBYY đọc sai dấu/chữ: 'dưới'→'dưđi', 'đốt'→'đót'.
        assertEquals("dudi mom gai dot", AnchorSimilarity.stripDiacritics("dưđi mỏm gai đót"))
        assertEquals("ABC", AnchorSimilarity.stripDiacritics("ĂBÇ").replace("Ç", "C"))
    }

    @Test
    fun ratioToleratesAbbyyMisreadAboveThreshold() {
        // Neo ABBYY vs sách Vision khác chủ yếu ở dấu → tương đồng cao sau khi bỏ dấu.
        val good = AnchorSimilarity.ratio("dưđi mỏm gai đót", "dưới mỏm gai đốt")
        assertTrue(good >= 0.8f, "ratio khớp gần đúng quá thấp: $good")
        val bad = AnchorSimilarity.ratio("dưđi mỏm gai đót", "một đoạn hoàn toàn khác")
        assertTrue(good > bad, "khớp đúng phải hơn khớp sai ($good vs $bad)")
    }

    @Test
    fun chooseBestPrefersExactOverFuzzy() {
        val cands = listOf(
            AnchorCandidate("exact", 0.90f, text = "", exact = true),
            AnchorCandidate("fuzzy", 0.41f, text = "dưới mỏm gai đốt", exact = false),
        )
        // Có ứng viên khớp ĐÚNG → chọn trong nhóm đúng (gần progress nhất), bỏ qua fuzzy.
        assertEquals(
            "exact",
            ReAnchorSelector.chooseBest(cands, target = 0.40f, snippet = "dưđi mỏm gai đót")?.cfi,
        )
    }

    @Test
    fun chooseBestFuzzyPicksNearestProgressAboveThreshold() {
        val snippet = "dưđi mỏm gai đót"
        val cands = listOf(
            AnchorCandidate("near", 0.42f, text = "dưới mỏm gai đốt", exact = false),
            AnchorCandidate("far", 0.80f, text = "dưới mỏm gai đốt", exact = false),
            AnchorCandidate("garbage", 0.41f, text = "chẳng liên quan gì", exact = false),
        )
        assertEquals(
            "near",
            ReAnchorSelector.chooseBest(cands, target = 0.40f, snippet = snippet, minSimilarity = 0.7f)?.cfi,
        )
    }

    @Test
    fun chooseBestReturnsNullWhenNoFuzzyAboveThreshold() {
        val cands = listOf(AnchorCandidate("g", 0.4f, text = "xyz khác hẳn", exact = false))
        assertNull(
            ReAnchorSelector.chooseBest(cands, target = 0.4f, snippet = "dưđi mỏm gai đót", minSimilarity = 0.7f),
        )
    }
}
