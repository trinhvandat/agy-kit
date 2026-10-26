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

/** Một kết quả khớp do foliate-js `search` trả về: CFI + vị trí thô trong sách (0..1). */
data class AnchorCandidate(val cfi: String, val progress: Float)

object ReAnchorSelector {
    /**
     * Khi `search` trả nhiều kết quả cho cùng snippet, chọn cái gần `target` nhất theo progress
     * (docs/04 §3 bước 3). Trả null nếu không có ứng viên.
     */
    fun chooseNearest(candidates: List<AnchorCandidate>, target: Float): AnchorCandidate? =
        candidates.minByOrNull { kotlin.math.abs(it.progress - target) }
}
