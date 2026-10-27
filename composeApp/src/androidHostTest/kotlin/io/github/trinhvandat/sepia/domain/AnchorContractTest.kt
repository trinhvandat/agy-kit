package io.github.trinhvandat.sepia.domain

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * HỢP ĐỒNG JS↔Kotlin cho neo vùng chọn. Dùng CHUNG fixture `scripts/fixtures/anchor_cases.json`
 * với test node (`scripts/test/anchor.test.mjs`).
 *
 * Bất biến: neo (prefix/text/suffix) do JS tạo (computeAnchor) — khi Kotlin nối lại qua
 * [AnchorText.fullQuery] — phải là CHUỖI CON của văn bản section đã chuẩn hoá ([AnchorText.normalize]).
 * Nhờ vậy re-anchor (foliate `search`) khớp. Lỗi 3a (mất space ranh giới) sẽ làm test này đỏ.
 */
class AnchorContractTest {
    @Serializable
    private data class Anchor(val prefix: String, val text: String, val suffix: String)

    @Serializable
    private data class Case(
        val name: String,
        val before: String,
        val selected: String,
        val after: String,
        val anchor: Anchor,
    )

    private val json = Json { ignoreUnknownKeys = true }

    private fun loadCases(): List<Case> {
        var dir: File? = File(System.getProperty("user.dir") ?: ".")
        repeat(6) {
            val f = dir?.resolve("scripts/fixtures/anchor_cases.json")
            if (f != null && f.exists()) return json.decodeFromString(f.readText())
            dir = dir?.parentFile
        }
        error("Không tìm thấy scripts/fixtures/anchor_cases.json từ ${System.getProperty("user.dir")}")
    }

    @Test
    fun fullQueryOfAnchorIsSubstringOfSection() {
        val cases = loadCases()
        assertTrue(cases.isNotEmpty(), "fixture rỗng")
        for (c in cases) {
            val anchor = TextAnchor(
                cfiRange = "",
                textSnippet = c.anchor.text,
                prefix = c.anchor.prefix,
                suffix = c.anchor.suffix,
                contentHash = "",
                progress = 0f,
            )
            val query = AnchorText.fullQuery(anchor)
            val section = AnchorText.normalize(c.before + c.selected + c.after)
            assertTrue(
                section.contains(query),
                "[${c.name}] fullQuery \"$query\" không nằm trong section \"$section\"",
            )
        }
    }

    @Test
    fun snippetQueryMatchesAnchorText() {
        for (c in loadCases()) {
            assertEquals(AnchorText.normalize(c.anchor.text), AnchorText.snippetQuery(
                TextAnchor("", c.anchor.text, c.anchor.prefix, c.anchor.suffix, "", 0f),
            ))
        }
    }
}
