package io.github.trinhvandat.sepia.content

import io.github.trinhvandat.sepia.data.BookRepository
import io.github.trinhvandat.sepia.data.ImportBookUseCase
import io.github.trinhvandat.sepia.domain.BookSource
import kotlinx.coroutines.CancellationException

/**
 * Đồng bộ content pack kèm sẵn trong APK lúc khởi động (docs/variants §content-pack):
 * sách mới → nhập; sách đổi (hash/pipelineVersion) → thay file (giữ vị trí đọc); sách không đổi → bỏ qua;
 * sách người dùng đã xóa → không tự thêm lại.
 */
class ContentPackSyncer(
    private val source: ContentPackSource?,
    private val repo: BookRepository,
    private val importBook: ImportBookUseCase,
    private val deleted: DeletedPackStore,
) {
    suspend fun sync(): ContentPackSyncReport {
        val manifest = source?.readManifest()
            ?: return ContentPackSyncReport(added = 0, replaced = 0, skipped = 0, skippedDeleted = 0, failed = 0)

        val deletedUids = deleted.deletedUids()
        var added = 0
        var replaced = 0
        var skipped = 0
        var skippedDeleted = 0
        var failed = 0

        for (entry in manifest.books) {
            try {
                if (entry.bookUid in deletedUids) {
                    skippedDeleted++
                    continue
                }

                val existing = repo.getByUid(entry.bookUid)
                if (existing == null) {
                    val bytes = requireNotNull(source.readEpub(entry.file)) {
                        "Không đọc được file pack: ${entry.file}"
                    }
                    importBook.import(bytes, entry.title, BookSource.Pack)
                    added++
                    continue
                }

                val changed = existing.contentHash != entry.sha256 || existing.pipelineVersion != entry.pipelineVersion
                if (changed) {
                    val bytes = requireNotNull(source.readEpub(entry.file)) {
                        "Không đọc được file pack: ${entry.file}"
                    }
                    importBook.import(bytes, entry.title, BookSource.Pack)
                    replaced++
                } else {
                    skipped++
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                failed++
            }
        }

        return ContentPackSyncReport(
            added = added,
            replaced = replaced,
            skipped = skipped,
            skippedDeleted = skippedDeleted,
            failed = failed,
        )
    }
}
