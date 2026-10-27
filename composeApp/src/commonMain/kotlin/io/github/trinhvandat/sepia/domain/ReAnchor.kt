package io.github.trinhvandat.sepia.domain

/**
 * Phần thuần Kotlin của re-anchor (ADR-008). Việc tìm CFI thật chạy trong JS (foliate-js `search`);
 * Kotlin chỉ (1) chuẩn hóa chuỗi trước khi so khớp, (2) chọn ứng viên tốt nhất khi `search` chỉ khớp
 * `textSnippet` và trả về nhiều kết quả (dự phòng R-01). Giữ thuần để test được không cần WebView.
 */
object AnchorText {
    private val whitespace = Regex("\\s+")

    /** NFC + gộp khoảng trắng (nhiều space/newline → một space), cắt đầu/cuối. */
    fun normalize(raw: String): String =
        normalizeNfc(raw).replace(whitespace, " ").trim()

    /** Chuỗi tìm kiếm đầy đủ prefix+snippet+suffix (đã chuẩn hóa) — thử khớp chính xác trước. */
    fun fullQuery(anchor: TextAnchor): String =
        normalize(anchor.prefix + anchor.textSnippet + anchor.suffix)

    /** Riêng textSnippet (đã chuẩn hóa) — chuỗi ngắn, ít vắt qua ranh giới đoạn (dự phòng). */
    fun snippetQuery(anchor: TextAnchor): String = normalize(anchor.textSnippet)
}

/**
 * Một kết quả khớp do foliate-js `search` trả về: CFI + vị trí thô (0..1) + text đã khớp + có phải
 * khớp **đúng** (diacritic-sensitive) không. `text`/`exact` phục vụ bước 3 (khớp gần đúng bỏ dấu).
 */
data class AnchorCandidate(
    val cfi: String,
    val progress: Float,
    val text: String = "",
    val exact: Boolean = false,
)

/**
 * So khớp **bỏ dấu** (docs/04 §3 bước 3): neo cũ (thường từ ABBYY) vs sách build lại (Vision) khác
 * nhau **chủ yếu ở dấu thanh/dấu phụ** ("dưới"→"dưđi", "đốt"→"đót"). Bỏ dấu + so Levenshtein cho
 * điểm tương đồng, dùng để nhận ra cùng một đoạn dù khác dấu. Thuần Kotlin (không `expect/actual`,
 * không Unicode normalize nền tảng) → tất định, chạy được trên cả Android lẫn iOS.
 */
object AnchorSimilarity {
    private val baseByAccent: Map<Char, Char> = buildMap {
        val groups = mapOf(
            'a' to "àáảãạăằắẳẵặâầấẩẫậ",
            'e' to "èéẻẽẹêềếểễệ",
            'i' to "ìíỉĩị",
            'o' to "òóỏõọôồốổỗộơờớởỡợ",
            'u' to "ùúủũụưừứửữự",
            'y' to "ỳýỷỹỵ",
            'd' to "đ",
        )
        for ((base, accents) in groups) {
            for (ch in accents) {
                put(ch, base)
                put(ch.uppercaseChar(), base.uppercaseChar())
            }
        }
    }

    /** Bỏ dấu thanh + dấu phụ nguyên âm + đ→d (giữ nguyên ký tự không phải tiếng Việt). */
    fun stripDiacritics(s: String): String = buildString(s.length) {
        for (c in s) append(baseByAccent[c] ?: c)
    }

    private fun canon(s: String): String = stripDiacritics(AnchorText.normalize(s)).lowercase()

    /** Tương đồng 0..1 giữa hai chuỗi sau khi chuẩn hoá + bỏ dấu (1 = giống hệt sau khi bỏ dấu). */
    fun ratio(a: String, b: String): Float {
        val x = canon(a)
        val y = canon(b)
        if (x.isEmpty() && y.isEmpty()) return 1f
        val maxLen = maxOf(x.length, y.length)
        if (maxLen == 0) return 0f
        return 1f - levenshtein(x, y).toFloat() / maxLen
    }

    private fun levenshtein(a: String, b: String): Int {
        if (a == b) return 0
        if (a.isEmpty()) return b.length
        if (b.isEmpty()) return a.length
        var prev = IntArray(b.length + 1) { it }
        var cur = IntArray(b.length + 1)
        for (i in 1..a.length) {
            cur[0] = i
            for (j in 1..b.length) {
                val cost = if (a[i - 1] == b[j - 1]) 0 else 1
                cur[j] = minOf(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
            }
            val tmp = prev; prev = cur; cur = tmp
        }
        return prev[b.length]
    }
}

object ReAnchorSelector {
    /**
     * Khi `search` trả nhiều kết quả cho cùng snippet, chọn cái gần `target` nhất theo progress
     * (docs/04 §3 bước 3). Trả null nếu không có ứng viên.
     */
    fun chooseNearest(candidates: List<AnchorCandidate>, target: Float): AnchorCandidate? =
        candidates.minByOrNull { kotlin.math.abs(it.progress - target) }

    /**
     * Chọn ứng viên re-anchor tốt nhất (docs/04 §3):
     *  - Có ứng viên khớp **ĐÚNG** (exact, diacritic-sensitive) → chọn trong nhóm đó, gần `target`
     *    nhất (bước 2 — tin tưởng, không cần xét tương đồng).
     *  - Không có → trong nhóm **gần đúng** (fuzzy), chỉ giữ ứng viên có tương đồng bỏ-dấu với
     *    `snippet` ≥ [minSimilarity] (bước 3), rồi chọn gần `target` nhất.
     *  - Không ứng viên nào đạt → null (gọi trả về sẽ `goToFraction(progress)`, bước 4, KHÔNG về đầu
     *    sách).
     */
    fun chooseBest(
        candidates: List<AnchorCandidate>,
        target: Float,
        snippet: String,
        minSimilarity: Float = 0.6f,
    ): AnchorCandidate? {
        val exact = candidates.filter { it.exact }
        val pool = if (exact.isNotEmpty()) {
            exact
        } else {
            candidates.filter { AnchorSimilarity.ratio(snippet, it.text) >= minSimilarity }
        }
        return pool.minByOrNull { kotlin.math.abs(it.progress - target) }
    }
}
