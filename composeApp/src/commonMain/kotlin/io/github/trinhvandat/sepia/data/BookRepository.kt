package io.github.trinhvandat.sepia.data

import io.github.trinhvandat.sepia.domain.Book
import kotlinx.coroutines.flow.Flow

/** Truy cập dữ liệu Book sau interface để đổi engine (ADR-002). */
interface BookRepository {
    /** Danh sách sách trong thư viện, phát lại khi dữ liệu đổi. */
    fun observeBooks(): Flow<List<Book>>

    suspend fun getById(id: String): Book?
    suspend fun getByUid(bookUid: String): Book?

    suspend fun insert(book: Book)

    /** Thay file + metadata cho cuốn cùng bookUid (giữ vị trí đọc/neo). */
    suspend fun replaceFileAndMeta(
        bookUid: String,
        title: String,
        author: String,
        filePath: String,
        coverPath: String?,
        contentHash: String,
        pipelineVersion: Int,
        sourcePdfName: String?,
    )

    /** Lưu vị trí đọc + neo (debounce khi relocated / app vào nền). */
    suspend fun savePosition(
        id: String,
        cfi: String?,
        snippet: String?,
        prefix: String?,
        suffix: String?,
        progress: Float,
        updatedAt: Long,
    )

    /** Cập nhật riêng CFI sau khi re-anchor thành công. */
    suspend fun updatePositionCfi(id: String, cfi: String, updatedAt: Long)

    suspend fun delete(id: String)

    /** sortIndex kế tiếp (cuối danh sách). */
    suspend fun nextSortIndex(): Int
}
