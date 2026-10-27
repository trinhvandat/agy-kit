package io.github.trinhvandat.sepia.data

import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import io.github.trinhvandat.sepia.db.SepiaDatabase
import io.github.trinhvandat.sepia.domain.Book
import io.github.trinhvandat.sepia.domain.Highlight
import io.github.trinhvandat.sepia.domain.HighlightStatus
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class HighlightRepositoryTest {
    private class Fixture {
        val driver = JdbcSqliteDriver(JdbcSqliteDriver.IN_MEMORY).also {
            SepiaDatabase.Schema.create(it)
            it.execute(null, "PRAGMA foreign_keys=ON", 0)
        }
        val db = SepiaDatabase(driver)
        val books = BookRepositoryImpl(db, Dispatchers.Unconfined)
        val repo = HighlightRepositoryImpl(db, Dispatchers.Unconfined)
    }

    private fun book(id: String, hash: String = "h1") = Book(
        id = id, bookUid = "sepia:$id", title = "T", author = "A", filePath = "/b/$id.epub",
        contentHash = hash, pipelineVersion = 1, addedAt = 1L, sortIndex = 0, positionUpdatedAt = 1L,
    )

    private fun hl(id: String, bookId: String = "b1", color: String = "yellow", progress: Float = 0.1f, hash: String = "h1") =
        Highlight(
            id = id, bookId = bookId, cfiRange = "cfi:$id", textSnippet = "đoạn $id",
            prefix = "trước ", suffix = " sau", contentHash = hash, color = color,
            progress = progress, createdAt = 1L, updatedAt = 1L,
        )

    @Test
    fun insertAndSelectByBookOrderedByProgress() = runTest {
        val f = Fixture()
        f.books.insert(book("b1"))
        f.repo.insert(hl("h2", progress = 0.5f))
        f.repo.insert(hl("h1", progress = 0.2f))
        val list = f.repo.observeByBook("b1").first()
        assertEquals(listOf("h1", "h2"), list.map { it.id })
        assertEquals("trước ", list[0].prefix)
        assertEquals(" sau", list[0].suffix)
    }

    @Test
    fun updateColorPersists() = runTest {
        val f = Fixture()
        f.books.insert(book("b1"))
        f.repo.insert(hl("h1", color = "yellow"))
        f.repo.updateColor("h1", "green", updatedAt = 2L)
        assertEquals("green", f.repo.getByBook("b1").single().color)
    }

    @Test
    fun markOrphanKeepsRowButChangesStatus() = runTest {
        val f = Fixture()
        f.books.insert(book("b1"))
        f.repo.insert(hl("h1"))
        f.repo.markOrphan("h1", updatedAt = 2L)
        val h = f.repo.getByBook("b1").single()
        assertEquals(HighlightStatus.ORPHAN, h.status)
    }

    @Test
    fun deleteRemovesHighlight() = runTest {
        val f = Fixture()
        f.books.insert(book("b1"))
        f.repo.insert(hl("h1"))
        f.repo.delete("h1")
        assertTrue(f.repo.getByBook("b1").isEmpty())
    }

    @Test
    fun deletingBookCascadesHighlights() = runTest {
        val f = Fixture()
        f.books.insert(book("b1"))
        f.repo.insert(hl("h1"))
        f.repo.insert(hl("h2"))
        f.books.delete("b1")
        assertTrue(f.repo.getByBook("b1").isEmpty(), "CASCADE: xóa Book phải xóa Highlight (foreign_keys ON)")
    }
}
