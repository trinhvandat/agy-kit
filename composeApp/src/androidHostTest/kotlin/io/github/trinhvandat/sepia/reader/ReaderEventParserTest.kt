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
             "rect":{"x":10.0,"y":20.0,"w":100.0,"h":18.5}}
        """.trimIndent()
        val event = ReaderEventParser.parse("selection", json)
        assertEquals(
            ReaderEvent.Selection(
                cfi = "epubcfi(/6/4!/2)",
                text = "Cá phê",
                prefix = "uống ",
                suffix = " nóng",
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
            ReaderEvent.ReanchorResult("pos", listOf("a", "b")),
            ReaderEventParser.parse("reanchorResult", """{"token":"pos","cfis":["a","b"]}"""),
        )
        assertEquals(
            ReaderEvent.Failure("open", "boom"),
            ReaderEventParser.parse("error", """{"where":"open","message":"boom"}"""),
        )
    }
}
