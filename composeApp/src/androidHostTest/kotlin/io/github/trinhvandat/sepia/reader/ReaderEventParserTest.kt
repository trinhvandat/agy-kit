package io.github.trinhvandat.sepia.reader

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull

class ReaderEventParserTest {
    @Test
    fun parsesTapZones() {
        assertEquals(ReaderEvent.Tap(TapZone.LEFT), ReaderEventParser.parse("tap", """{"zone":"left"}"""))
        assertEquals(ReaderEvent.Tap(TapZone.CENTER), ReaderEventParser.parse("tap", """{"zone":"center"}"""))
        assertEquals(ReaderEvent.Tap(TapZone.RIGHT), ReaderEventParser.parse("tap", """{"zone":"right"}"""))
    }

    @Test
    fun tapWithUnknownZoneBecomesFailureNotCrash() {
        val event = assertIs<ReaderEvent.Failure>(ReaderEventParser.parse("tap", """{"zone":"middle"}"""))
        assertEquals("tap", event.where)
    }

    @Test
    fun parsesSelectionWithRectAndAnchor() {
        val json = """
            {"cfi":"epubcfi(/6/4!/2)","text":"Cá phê","prefix":"uống ","suffix":" nóng",
             "fraction":0.42,"rect":{"x":10.0,"y":20.0,"w":100.0,"h":18.5}}
        """.trimIndent()
        val event = ReaderEventParser.parse("selection", json)
        assertEquals(
            ReaderEvent.Selection(
                cfi = "epubcfi(/6/4!/2)",
                text = "Cá phê",
                prefix = "uống ",
                suffix = " nóng",
                fraction = 0.42f,
                rect = SelectionRect(10f, 20f, 100f, 18.5f),
            ),
            event,
        )
    }

    @Test
    fun selectionWithMissingRectUsesZeroRect() {
        val event = assertIs<ReaderEvent.Selection>(
            ReaderEventParser.parse("selection", """{"cfi":"c","text":"t","prefix":"","suffix":""}"""),
        )
        assertEquals(SelectionRect(0f, 0f, 0f, 0f), event.rect)
    }

    @Test
    fun parsesSelectionCleared() {
        assertEquals(ReaderEvent.SelectionCleared, ReaderEventParser.parse("selectionCleared", "{}"))
    }

    @Test
    fun parsesHighlightTap() {
        assertEquals(
            ReaderEvent.HighlightTap("abc", SelectionRect(5f, 6f, 7f, 8f)),
            ReaderEventParser.parse("highlightTap", """{"id":"abc","rect":{"x":5,"y":6,"w":7,"h":8}}"""),
        )
    }

    @Test
    fun malformedSelectionPayloadBecomesFailureNotCrash() {
        // rect sai kiểu (string thay vì object) → Failure, không ném.
        val event = assertIs<ReaderEvent.Failure>(
            ReaderEventParser.parse("selection", """{"cfi":"c","rect":"nope"}"""),
        )
        assertEquals("selection", event.where)
    }

    @Test
    fun unknownMethodReturnsNull() {
        assertNull(ReaderEventParser.parse("somethingElse", "{}"))
    }

    @Test
    fun stillParsesExistingEvents() {
        assertEquals(ReaderEvent.BridgeReady, ReaderEventParser.parse("bridgeReady", "{}"))
        assertEquals(ReaderEvent.SelectionCleared, ReaderEventParser.parse("selectionCleared", "{}"))
        assertEquals(
            ReaderEvent.Ready("epubcfi(/2)"),
            ReaderEventParser.parse("ready", """{"restoredCfi":"epubcfi(/2)"}"""),
        )
        assertEquals(ReaderEvent.Ready(null), ReaderEventParser.parse("ready", """{"restoredCfi":""}"""))
        assertEquals(
            ReaderEvent.Relocated("c", 0.5f, "s", "p", "x"),
            ReaderEventParser.parse(
                "relocated",
                """{"cfi":"c","fraction":0.5,"snippet":"s","prefix":"p","suffix":"x"}""",
            ),
        )
        assertEquals(
            ReaderEvent.Failure("open", "boom"),
            ReaderEventParser.parse("error", """{"where":"open","message":"boom"}"""),
        )
    }

    @Test
    fun parsesReanchorCandidatesWithProgressTextExact() {
        val json = """
            {"token":"pos","candidates":[
              {"cfi":"a","progress":0.12,"text":"đỏ thì dừng","exact":true},
              {"cfi":"b","progress":0.55,"text":"đo thi dưng","exact":false}
            ]}
        """.trimIndent()
        val event = assertIs<ReaderEvent.ReanchorResult>(ReaderEventParser.parse("reanchorResult", json))
        assertEquals("pos", event.token)
        assertEquals(2, event.candidates.size)
        assertEquals("a", event.candidates[0].cfi)
        assertEquals(0.12f, event.candidates[0].progress)
        assertEquals("đỏ thì dừng", event.candidates[0].text)
        assertEquals(true, event.candidates[0].exact)
        assertEquals(false, event.candidates[1].exact)
    }

    @Test
    fun relocatedWithNullFractionBecomesZeroNotFailure() {
        // foliate có thể phát relocate với fraction=NaN lúc mở ở đầu sách → JSON.stringify → null.
        // Parser phải coi null là 0 (coerceInputValues), KHÔNG Failure (tránh banner lỗi — Việc 2).
        val event = assertIs<ReaderEvent.Relocated>(
            ReaderEventParser.parse(
                "relocated",
                """{"cfi":"epubcfi(/6/2!/4)","fraction":null,"snippet":"","prefix":"","suffix":""}""",
            ),
        )
        assertEquals(0f, event.fraction)
        assertEquals("epubcfi(/6/2!/4)", event.cfi)
    }

    @Test
    fun parsesEmptyReanchorCandidates() {
        val event = assertIs<ReaderEvent.ReanchorResult>(
            ReaderEventParser.parse("reanchorResult", """{"token":"pos","candidates":[]}"""),
        )
        assertEquals(0, event.candidates.size)
    }

    @Test
    fun readyWithCfiFailedTrueParsesFlag() {
        // bridge.js open() báo cfiFailed=true khi CFI lưu cũ không còn khớp DOM (content-pack đổi) →
        // Kotlin phải thấy được cờ này để kích hoạt re-anchor dự phòng (ADR-008).
        assertEquals(
            ReaderEvent.Ready(null, cfiFailed = true),
            ReaderEventParser.parse("ready", """{"restoredCfi":"","cfiFailed":true}"""),
        )
    }

    @Test
    fun parsesTocTreeWithLevelsAndChildren() {
        val json = """
            {"items":[
              {"label":"Phần I","href":"p1.xhtml","level":1,"children":[
                {"label":"Giác hơi","href":"p1.xhtml#a","level":2}
              ]},
              {"label":"Phần II","href":"p2.xhtml","level":1}
            ]}
        """.trimIndent()
        val event = assertIs<ReaderEvent.Toc>(ReaderEventParser.parse("toc", json))
        assertEquals(2, event.items.size)
        assertEquals("Phần I", event.items[0].label)
        assertEquals(1, event.items[0].level)
        assertEquals("Giác hơi", event.items[0].children.single().label)
        assertEquals(2, event.items[0].children.single().level)
        assertEquals(0, event.items[1].children.size)
    }

    @Test
    fun parsesEmptyToc() {
        val event = assertIs<ReaderEvent.Toc>(ReaderEventParser.parse("toc", """{"items":[]}"""))
        assertEquals(0, event.items.size)
    }

    @Test
    fun parsesLinkJump() {
        val event = assertIs<ReaderEvent.LinkJump>(
            ReaderEventParser.parse("link", """{"cfi":"epubcfi(/6/8!/2)"}"""),
        )
        assertEquals("epubcfi(/6/8!/2)", event.fromCfi)
    }

    @Test
    fun relocatedCarriesTocLabelAndHref() {
        val event = assertIs<ReaderEvent.Relocated>(
            ReaderEventParser.parse(
                "relocated",
                """{"cfi":"c","fraction":0.3,"snippet":"s","prefix":"p","suffix":"x",
                   "tocLabel":"Chương 2","tocHref":"c2.xhtml"}""",
            ),
        )
        assertEquals("Chương 2", event.tocLabel)
        assertEquals("c2.xhtml", event.tocHref)
    }

    @Test
    fun relocatedWithoutTocFieldsDefaultsEmpty() {
        val event = assertIs<ReaderEvent.Relocated>(
            ReaderEventParser.parse(
                "relocated",
                """{"cfi":"c","fraction":0.5,"snippet":"s","prefix":"p","suffix":"x"}""",
            ),
        )
        assertEquals("", event.tocLabel)
        assertEquals("", event.tocHref)
    }

    @Test
    fun readyWithoutCfiFailedFieldDefaultsFalse() {
        // Tương thích ngược: thông điệp 'ready' cũ (trước fix) không có field này vẫn phải parse được.
        assertEquals(
            ReaderEvent.Ready("epubcfi(/2)", cfiFailed = false),
            ReaderEventParser.parse("ready", """{"restoredCfi":"epubcfi(/2)"}"""),
        )
    }
}
