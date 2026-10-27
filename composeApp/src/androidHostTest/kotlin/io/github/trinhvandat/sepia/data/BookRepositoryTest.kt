package io.github.trinhvandat.sepia.data

import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import io.github.trinhvandat.sepia.db.SepiaDatabase
import io.github.trinhvandat.sepia.domain.Book
import io.github.trinhvandat.sepia.domain.BookSource
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class BookRepositoryTest {
    private fun repo(): BookRepository {
        val driver = JdbcSqliteDriver(JdbcSqliteDriver.IN_MEMORY)
        SepiaDatabase.Schema.create(driver)
        return BookRepositoryImpl(SepiaDatabase(driver), Dispatchers.Unconfined)
    }

    private fun book(id: String, uid: String, sort: Int = 0) = Book(
        id = id, bookUid = uid, title = "T$id", author = "A", filePath = "/b/$id.epub",
        contentHash = "h$id", pipelineVersion = 1, addedAt = 100L, sortIndex = sort,
        positionUpdatedAt = 100L,
    )

    @Test
    fun insertAndQueryByUid() = runTest {
        val repo = repo()
        repo.insert(book("1", "sepia:a"))
        assertEquals("sepia:a", repo.getByUid("sepia:a")?.bookUid)
        assertEquals("T1", repo.getById("1")?.title)
        assertNull(repo.getByUid("missing"))
    }

    @Test
    fun observeBooksOrdersBySortIndex() = runTest {
        val repo = repo()
        repo.insert(book("1", "sepia:a", sort = 1))
        repo.insert(book("2", "sepia:b", sort = 0))
        val list = repo.observeBooks().first()
        assertEquals(listOf("2", "1"), list.map { it.id })
    }

    @Test
    fun nextSortIndexIncrements() = runTest {
        val repo = repo()
        assertEquals(0, repo.nextSortIndex())
        repo.insert(book("1", "sepia:a", sort = repo.nextSortIndex()))
        assertEquals(1, repo.nextSortIndex())
    }

    @Test
    fun savePositionPersists() = runTest {
        val repo = repo()
        repo.insert(book("1", "sepia:a"))
        repo.savePosition("1", "epubcfi(/6/2)", "snip", "pre", "suf", 0.5f, 200L)
        val b = repo.getById("1")!!
        assertEquals("epubcfi(/6/2)", b.positionCfi)
        assertEquals("snip", b.positionSnippet)
        assertEquals(0.5f, b.progress)
        assertEquals(50, b.progressPercent)
    }

    @Test
    fun replaceFileAndMetaKeepsPosition() = runTest {
        val repo = repo()
        repo.insert(book("1", "sepia:a"))
        repo.savePosition("1", "cfi", "snip", "pre", "suf", 0.3f, 200L)
        repo.replaceFileAndMeta("sepia:a", "T-new", "A2", "/b/1.epub", null, "h-new", 3, "src.pdf")
        val b = repo.getById("1")!!
        assertEquals("T-new", b.title)
        assertEquals("h-new", b.contentHash)
        assertEquals(3, b.pipelineVersion)
        assertEquals("cfi", b.positionCfi, "vị trí đọc phải được giữ nguyên")
        assertEquals(0.3f, b.progress)
    }

    @Test
    fun deleteRemoves() = runTest {
        val repo = repo()
        val b = book("1", "sepia:a")
        repo.insert(b)
        repo.delete(b)
        assertTrue(repo.observeBooks().first().isEmpty())
    }

    @Test
    fun deletingPackBookWritesTombstone() = runTest {
        val repo = repo()
        val b = book("1", "sepia:a").copy(source = BookSource.Pack)
        repo.insert(b)
        repo.delete(b)
        assertTrue(repo.observeBooks().first().isEmpty())
        assertEquals(setOf("sepia:a"), repo.deletedPackUids())
    }

    @Test
    fun deletingImportBookDoesNotWriteTombstone() = runTest {
        val repo = repo()
        val b = book("1", "sepia:a")
        repo.insert(b)
        repo.delete(b)
        assertTrue(repo.deletedPackUids().isEmpty())
    }

    @Test
    fun markPackDeletedAndDeletedPackUidsRoundTrip() = runTest {
        val repo = repo()
        repo.markPackDeleted("sepia:x")
        assertEquals(setOf("sepia:x"), repo.deletedPackUids())
    }
}
