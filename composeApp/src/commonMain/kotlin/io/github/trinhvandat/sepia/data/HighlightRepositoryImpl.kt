package io.github.trinhvandat.sepia.data

import app.cash.sqldelight.coroutines.asFlow
import app.cash.sqldelight.coroutines.mapToList
import io.github.trinhvandat.sepia.db.SepiaDatabase
import io.github.trinhvandat.sepia.domain.Highlight
import io.github.trinhvandat.sepia.domain.HighlightKind
import io.github.trinhvandat.sepia.domain.HighlightStatus
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.withContext

/** Hiện thực HighlightRepository bằng SQLDelight. Chạy truy vấn ngoài main qua [dispatcher]. */
class HighlightRepositoryImpl(
    db: SepiaDatabase,
    private val dispatcher: CoroutineDispatcher,
) : HighlightRepository {
    private val q = db.highlightQueries

    override fun observeByBook(bookId: String): Flow<List<Highlight>> =
        q.selectByBook(bookId, ::mapRow).asFlow().mapToList(dispatcher)

    override suspend fun getByBook(bookId: String): List<Highlight> =
        withContext(dispatcher) { q.selectByBook(bookId, ::mapRow).executeAsList() }

    override suspend fun insert(highlight: Highlight): Unit = withContext(dispatcher) {
        q.insert(
            id = highlight.id,
            bookId = highlight.bookId,
            kind = highlight.kind.id,
            cfiRange = highlight.cfiRange,
            textSnippet = highlight.textSnippet,
            prefix = highlight.prefix,
            suffix = highlight.suffix,
            contentHash = highlight.contentHash,
            color = highlight.color,
            note = highlight.note,
            status = highlight.status.id,
            progress = highlight.progress.toDouble(),
            createdAt = highlight.createdAt,
            updatedAt = highlight.updatedAt,
        )
    }

    override suspend fun updateColor(id: String, color: String, updatedAt: Long): Unit =
        withContext(dispatcher) { q.updateColor(color = color, updatedAt = updatedAt, id = id) }

    override suspend fun markOrphan(id: String, updatedAt: Long): Unit =
        withContext(dispatcher) { q.markOrphan(updatedAt = updatedAt, id = id) }

    override suspend fun delete(id: String): Unit =
        withContext(dispatcher) { q.delete(id) }

    private fun mapRow(
        id: String,
        bookId: String,
        kind: String,
        cfiRange: String,
        textSnippet: String,
        prefix: String,
        suffix: String,
        contentHash: String,
        color: String,
        note: String?,
        status: String,
        progress: Double,
        createdAt: Long,
        updatedAt: Long,
    ): Highlight = Highlight(
        id = id,
        bookId = bookId,
        kind = HighlightKind.fromId(kind),
        cfiRange = cfiRange,
        textSnippet = textSnippet,
        prefix = prefix,
        suffix = suffix,
        contentHash = contentHash,
        color = color,
        note = note,
        status = HighlightStatus.fromId(status),
        progress = progress.toFloat(),
        createdAt = createdAt,
        updatedAt = updatedAt,
    )
}
