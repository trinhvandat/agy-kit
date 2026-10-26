package io.github.trinhvandat.sepia.domain

/**
 * Metadata đọc từ file EPUB (OPF). Pipeline Sepia ghi:
 * - `dc:identifier` = `sepia:<sha256 PDF gốc>` → [bookUid] ổn định giữa các lần build (docs/04 §6).
 * - `<meta property="sepia:pipeline-version">` → [pipelineVersion].
 * - `<meta property="sepia:source-pdf">` → [sourcePdfName].
 */
data class EpubMetadata(
    val bookUid: String?,        // chỉ khác null khi dc:identifier bắt đầu bằng "sepia:"
    val rawIdentifier: String?,  // dc:identifier nguyên gốc (có thể là urn:uuid… với sách ngoài)
    val title: String,
    val author: String,
    val pipelineVersion: Int,
    val sourcePdfName: String?,
) {
    /** EPUB do pipeline Sepia tạo (re-anchor xuyên-build mới đáng tin). */
    val isSepiaBook: Boolean get() = bookUid != null

    /**
     * Khóa khử trùng ổn định. Sách Sepia → `sepia:`; sách ngoài có identifier riêng → dùng nó;
     * không có identifier → bám theo hash nội dung (docs/04 §6 bước 3).
     */
    fun effectiveUid(contentHash: String): String =
        bookUid ?: rawIdentifier?.takeIf { it.isNotBlank() } ?: "sha256:$contentHash"
}
