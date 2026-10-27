package io.github.trinhvandat.sepia.data

import io.github.trinhvandat.sepia.domain.Book
import io.github.trinhvandat.sepia.domain.BookSource
import io.github.trinhvandat.sepia.domain.ImportOutcome

/**
 * Nhập một file EPUB & khử trùng theo bookUid (docs/04 §6).
 * Logic thuần (phụ thuộc repo + fileStore + reader đã trừu tượng) → test được với fake.
 */
class ImportBookUseCase(
    private val repo: BookRepository,
    private val metadataReader: EpubMetadataReader,
    private val fileStore: BookFileStore,
) {
    suspend fun import(
        epubBytes: ByteArray,
        fallbackTitle: String,
        source: BookSource = BookSource.Import,
    ): ImportOutcome {
        val meta = metadataReader.read(epubBytes)
        val contentHash = sha256Hex(epubBytes)
        val bookUid = meta.effectiveUid(contentHash)
        val now = nowMillis()
        val title = meta.title.ifBlank { fallbackTitle }

        val existing = repo.getByUid(bookUid)
        if (existing == null) {
            val id = randomUuid()
            val path = fileStore.pathForNewBook(id)
            fileStore.writeEpub(path, epubBytes)
            val book = Book(
                id = id,
                bookUid = bookUid,
                title = title,
                author = meta.author,
                filePath = path,
                coverPath = null,
                contentHash = contentHash,
                pipelineVersion = meta.pipelineVersion,
                sourcePdfName = meta.sourcePdfName,
                source = source,
                addedAt = now,
                sortIndex = repo.nextSortIndex(),
                positionUpdatedAt = now,
            )
            repo.insert(book)
            return ImportOutcome.Created(book, external = !meta.isSepiaBook)
        }

        // Cùng bookUid → thay file (đè cùng path), GIỮ vị trí đọc + neo (positionSnippet/prefix/suffix).
        val contentChanged = existing.contentHash != contentHash
        fileStore.writeEpub(existing.filePath, epubBytes)
        repo.replaceFileAndMeta(
            bookUid = bookUid,
            title = title,
            author = meta.author,
            filePath = existing.filePath,
            coverPath = existing.coverPath,
            contentHash = contentHash,
            pipelineVersion = meta.pipelineVersion,
            sourcePdfName = meta.sourcePdfName,
        )
        val updated = existing.copy(
            title = title,
            author = meta.author,
            contentHash = contentHash,
            pipelineVersion = meta.pipelineVersion,
            sourcePdfName = meta.sourcePdfName,
        )
        return ImportOutcome.Replaced(updated, contentChanged = contentChanged)
    }
}
