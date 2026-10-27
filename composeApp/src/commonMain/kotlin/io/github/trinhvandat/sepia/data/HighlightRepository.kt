package io.github.trinhvandat.sepia.data

import io.github.trinhvandat.sepia.domain.Highlight
import kotlinx.coroutines.flow.Flow

/** Truy cập dữ liệu Highlight sau interface (ADR-002). Người dùng tự xóa; hệ thống KHÔNG tự xóa. */
interface HighlightRepository {
    /** Highlight của một cuốn, phát lại khi dữ liệu đổi (để vẽ lại trên màn đọc). */
    fun observeByBook(bookId: String): Flow<List<Highlight>>

    suspend fun getByBook(bookId: String): List<Highlight>

    suspend fun insert(highlight: Highlight)

    suspend fun updateColor(id: String, color: String, updatedAt: Long)

    /** Re-anchor thất bại (Mốc 3e): đánh dấu mồ côi, KHÔNG xóa. */
    suspend fun markOrphan(id: String, updatedAt: Long)

    suspend fun delete(id: String)
}
