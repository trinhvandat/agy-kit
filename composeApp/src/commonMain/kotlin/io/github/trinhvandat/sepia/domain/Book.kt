package io.github.trinhvandat.sepia.domain

/**
 * Một cuốn sách trong thư viện + vị trí đọc hiện tại (docs/04 §2).
 * Trung tính về lĩnh vực; không nhúng nội dung EPUB (nội dung ở file `.epub`).
 * Các cột vị trí để phẳng (1:1 với bảng Book) cho dễ map; dựng [TextAnchor] khi cần re-anchor.
 */
data class Book(
    val id: String,
    val bookUid: String,
    val title: String,
    val author: String,
    val filePath: String,
    val coverPath: String? = null,
    val contentHash: String,
    val pipelineVersion: Int,
    val sourcePdfName: String? = null,
    val source: BookSource = BookSource.Import,
    val addedAt: Long,
    val sortIndex: Int,
    val positionCfi: String? = null,
    val positionSnippet: String? = null,
    val positionPrefix: String? = null,
    val positionSuffix: String? = null,
    val progress: Float = 0f,
    val positionUpdatedAt: Long = 0L,
) {
    /** % tiến độ 0..100 để hiển thị thư viện (US-E3). */
    val progressPercent: Int get() = (progress.coerceIn(0f, 1f) * 100).toInt()

    /** Neo vị trí đọc để re-anchor (null nếu chưa từng đọc / thiếu snippet). */
    fun readingAnchor(): TextAnchor? {
        val snippet = positionSnippet ?: return null
        return TextAnchor(
            cfiRange = positionCfi.orEmpty(),
            textSnippet = snippet,
            prefix = positionPrefix.orEmpty(),
            suffix = positionSuffix.orEmpty(),
            contentHash = contentHash,
            progress = progress,
        )
    }
}
