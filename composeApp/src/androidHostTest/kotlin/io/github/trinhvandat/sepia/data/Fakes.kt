package io.github.trinhvandat.sepia.data

import io.github.trinhvandat.sepia.domain.Book
import io.github.trinhvandat.sepia.domain.BookSource
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

/** BookRepository trong bộ nhớ cho test logic import (không đụng DB thật). */
class InMemoryBookRepository : BookRepository {
    private val state = MutableStateFlow<List<Book>>(emptyList())
    private val deletedUids = mutableSetOf<String>()
    private val byId get() = state.value.associateBy { it.id }

    override fun observeBooks(): Flow<List<Book>> = state.asStateFlow()
    override suspend fun getById(id: String): Book? = byId[id]
    override suspend fun getByUid(bookUid: String): Book? = state.value.firstOrNull { it.bookUid == bookUid }

    override suspend fun insert(book: Book) {
        state.value = state.value + book
    }

    override suspend fun replaceFileAndMeta(
        bookUid: String,
        title: String,
        author: String,
        filePath: String,
        coverPath: String?,
        contentHash: String,
        pipelineVersion: Int,
        sourcePdfName: String?,
    ) {
        state.value = state.value.map {
            if (it.bookUid == bookUid) it.copy(
                title = title, author = author, filePath = filePath, coverPath = coverPath,
                contentHash = contentHash, pipelineVersion = pipelineVersion, sourcePdfName = sourcePdfName,
            ) else it
        }
    }

    override suspend fun savePosition(
        id: String, cfi: String?, snippet: String?, prefix: String?, suffix: String?,
        progress: Float, updatedAt: Long,
    ) {
        state.value = state.value.map {
            if (it.id == id) it.copy(
                positionCfi = cfi, positionSnippet = snippet, positionPrefix = prefix,
                positionSuffix = suffix, progress = progress, positionUpdatedAt = updatedAt,
            ) else it
        }
    }

    override suspend fun updatePositionCfi(id: String, cfi: String, updatedAt: Long) {
        state.value = state.value.map {
            if (it.id == id) it.copy(positionCfi = cfi, positionUpdatedAt = updatedAt) else it
        }
    }

    override suspend fun delete(book: Book) {
        if (book.source == BookSource.Pack) {
            deletedUids.add(book.bookUid)
        }
        state.value = state.value.filterNot { it.id == book.id }
    }

    override suspend fun nextSortIndex(): Int = (state.value.maxOfOrNull { it.sortIndex } ?: -1) + 1

    override suspend fun markPackDeleted(bookUid: String) {
        deletedUids.add(bookUid)
    }

    override suspend fun deletedPackUids(): Set<String> = deletedUids.toSet()
}

/** BookFileStore giả: nhớ các lần ghi, không chạm hệ thống file. */
class FakeBookFileStore : BookFileStore {
    val written = mutableMapOf<String, ByteArray>()
    override fun pathForNewBook(id: String): String = "/fake/books/$id.epub"
    override fun writeEpub(path: String, bytes: ByteArray) { written[path] = bytes }
    override fun deleteFile(path: String) { written.remove(path) }
}
