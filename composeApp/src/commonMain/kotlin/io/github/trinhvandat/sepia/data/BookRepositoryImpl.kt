package io.github.trinhvandat.sepia.data

import app.cash.sqldelight.coroutines.asFlow
import app.cash.sqldelight.coroutines.mapToList
import io.github.trinhvandat.sepia.db.SepiaDatabase
import io.github.trinhvandat.sepia.domain.Book
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.withContext

/** Hiện thực BookRepository bằng SQLDelight. Chạy truy vấn ngoài main qua [dispatcher]. */
class BookRepositoryImpl(
    db: SepiaDatabase,
    private val dispatcher: CoroutineDispatcher,
) : BookRepository {
    private val q = db.bookQueries

    override fun observeBooks(): Flow<List<Book>> =
        q.selectAll(::mapRow).asFlow().mapToList(dispatcher)

    override suspend fun getById(id: String): Book? =
        withContext(dispatcher) { q.selectById(id, ::mapRow).executeAsOneOrNull() }

    override suspend fun getByUid(bookUid: String): Book? =
        withContext(dispatcher) { q.selectByUid(bookUid, ::mapRow).executeAsOneOrNull() }

    override suspend fun insert(book: Book): Unit = withContext(dispatcher) {
        q.insert(
            id = book.id,
            bookUid = book.bookUid,
            title = book.title,
            author = book.author,
            filePath = book.filePath,
            coverPath = book.coverPath,
            contentHash = book.contentHash,
            pipelineVersion = book.pipelineVersion.toLong(),
            sourcePdfName = book.sourcePdfName,
            addedAt = book.addedAt,
            sortIndex = book.sortIndex.toLong(),
            positionCfi = book.positionCfi,
            positionSnippet = book.positionSnippet,
            positionPrefix = book.positionPrefix,
            positionSuffix = book.positionSuffix,
            progress = book.progress.toDouble(),
            positionUpdatedAt = book.positionUpdatedAt,
        )
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
    ): Unit = withContext(dispatcher) {
        q.replaceFileAndMeta(
            title = title,
            author = author,
            filePath = filePath,
            coverPath = coverPath,
            contentHash = contentHash,
            pipelineVersion = pipelineVersion.toLong(),
            sourcePdfName = sourcePdfName,
            bookUid = bookUid,
        )
    }

    override suspend fun savePosition(
        id: String,
        cfi: String?,
        snippet: String?,
        prefix: String?,
        suffix: String?,
        progress: Float,
        updatedAt: Long,
    ): Unit = withContext(dispatcher) {
        q.updatePosition(
            positionCfi = cfi,
            positionSnippet = snippet,
            positionPrefix = prefix,
            positionSuffix = suffix,
            progress = progress.toDouble(),
            positionUpdatedAt = updatedAt,
            id = id,
        )
    }

    override suspend fun updatePositionCfi(id: String, cfi: String, updatedAt: Long): Unit =
        withContext(dispatcher) { q.updatePositionCfi(cfi, updatedAt, id) }

    override suspend fun delete(id: String): Unit =
        withContext(dispatcher) { q.delete(id) }

    override suspend fun nextSortIndex(): Int =
        withContext(dispatcher) { q.maxSortIndex().executeAsOne().toInt() + 1 }

    // SQLDelight mapper: hàng DB → domain Book (Long→Int, Double→Float).
    private fun mapRow(
        id: String,
        bookUid: String,
        title: String,
        author: String,
        filePath: String,
        coverPath: String?,
        contentHash: String,
        pipelineVersion: Long,
        sourcePdfName: String?,
        addedAt: Long,
        sortIndex: Long,
        positionCfi: String?,
        positionSnippet: String?,
        positionPrefix: String?,
        positionSuffix: String?,
        progress: Double,
        positionUpdatedAt: Long,
    ): Book = Book(
        id = id,
        bookUid = bookUid,
        title = title,
        author = author,
        filePath = filePath,
        coverPath = coverPath,
        contentHash = contentHash,
        pipelineVersion = pipelineVersion.toInt(),
        sourcePdfName = sourcePdfName,
        addedAt = addedAt,
        sortIndex = sortIndex.toInt(),
        positionCfi = positionCfi,
        positionSnippet = positionSnippet,
        positionPrefix = positionPrefix,
        positionSuffix = positionSuffix,
        progress = progress.toFloat(),
        positionUpdatedAt = positionUpdatedAt,
    )
}
