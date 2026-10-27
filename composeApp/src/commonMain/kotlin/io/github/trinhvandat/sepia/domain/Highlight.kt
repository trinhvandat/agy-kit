package io.github.trinhvandat.sepia.domain

/** Loại neo (docs/04 §2). `note`/`bookmark` có thể có cfiRange độ dài 0. */
enum class HighlightKind(val id: String) {
    HIGHLIGHT("highlight"),
    NOTE("note"),
    BOOKMARK("bookmark"),
    ;

    companion object {
        fun fromId(id: String): HighlightKind = entries.firstOrNull { it.id == id } ?: HIGHLIGHT
    }
}

/** Trạng thái neo: `orphan` = không re-anchor được nhưng KHÔNG xóa (NFR-3). */
enum class HighlightStatus(val id: String) {
    ACTIVE("active"),
    ORPHAN("orphan"),
    ;

    companion object {
        fun fromId(id: String): HighlightStatus = entries.firstOrNull { it.id == id } ?: ACTIVE
    }
}

/**
 * Một Highlight (gộp cả Note/Bookmark — docs/04 §1-2). Trung tính về lĩnh vực.
 * Neo bền: [textSnippet] + [prefix] + [suffix] + [contentHash] để re-anchor khi EPUB build lại (§3).
 * [color] là id trong bảng màu lõi (HighlightColor); [note] cho Mốc 3c.
 */
data class Highlight(
    val id: String,
    val bookId: String,
    val kind: HighlightKind = HighlightKind.HIGHLIGHT,
    val cfiRange: String,
    val textSnippet: String,
    val prefix: String,
    val suffix: String,
    val contentHash: String,
    val color: String,
    val note: String? = null,
    val status: HighlightStatus = HighlightStatus.ACTIVE,
    val progress: Float = 0f,
    val createdAt: Long,
    val updatedAt: Long,
) {
    /** Neo văn bản để re-anchor (dùng chung thuật toán với vị trí đọc). */
    fun anchor(): TextAnchor = TextAnchor(
        cfiRange = cfiRange,
        textSnippet = textSnippet,
        prefix = prefix,
        suffix = suffix,
        contentHash = contentHash,
        progress = progress,
    )
}
