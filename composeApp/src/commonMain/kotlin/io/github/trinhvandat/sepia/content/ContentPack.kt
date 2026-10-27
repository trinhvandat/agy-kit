package io.github.trinhvandat.sepia.content

import kotlinx.serialization.Serializable

/**
 * Manifest kèm sẵn trong APK mô tả các sách thuộc content pack (bật bằng VariantConfig).
 * Việc parse JSON thực tế nằm ở lớp Android (Task 8); lớp này chỉ là model trung tính.
 */
@Serializable
data class ContentPackManifest(
    val packVersion: Int = 1,
    val books: List<ContentPackBook> = emptyList(),
)

@Serializable
data class ContentPackBook(
    val bookUid: String,
    val title: String,
    val author: String = "",
    val file: String,
    val sha256: String,
    val pipelineVersion: Int,
    val sourcePdfName: String? = null,
)

/** Nguồn đọc manifest + nội dung EPUB của content pack (null trên nền tảng chưa có pack). */
interface ContentPackSource {
    /** @return null khi không có pack kèm theo (ví dụ biến thể không bật content pack). */
    suspend fun readManifest(): ContentPackManifest?

    /** @return null khi không đọc được file EPUB tương ứng. */
    suspend fun readEpub(file: String): ByteArray?
}

/** Tập bookUid sách pack người dùng đã xóa (không tự thêm lại — docs/04). */
interface DeletedPackStore {
    suspend fun deletedUids(): Set<String>
}

/** Kết quả một lần đồng bộ content pack. */
data class ContentPackSyncReport(
    val added: Int,
    val replaced: Int,
    val skipped: Int,
    val skippedDeleted: Int,
    val failed: Int,
)
