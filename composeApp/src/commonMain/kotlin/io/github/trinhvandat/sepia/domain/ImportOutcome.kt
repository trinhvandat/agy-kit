package io.github.trinhvandat.sepia.domain

/** Kết quả nhập một file EPUB (docs/04 §6). */
sealed interface ImportOutcome {
    val book: Book

    /**
     * Sách mới (bookUid chưa có trong thư viện).
     * @param external EPUB không có `dc:identifier` dạng `sepia:` → re-anchor xuyên-build không đáng tin
     *                 (cảnh báo người dùng — docs/04 §6 bước 3).
     */
    data class Created(override val book: Book, val external: Boolean) : ImportOutcome

    /**
     * Cùng bookUid đã có → thay file + cập nhật metadata, GIỮ vị trí đọc & highlight.
     * @param contentChanged file EPUB khác bản cũ (contentHash đổi) → cần re-anchor khi mở (ADR-008).
     */
    data class Replaced(override val book: Book, val contentChanged: Boolean) : ImportOutcome
}
