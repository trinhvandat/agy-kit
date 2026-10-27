package io.github.trinhvandat.sepia.content

import io.github.trinhvandat.sepia.data.EpubMetadataReader
import io.github.trinhvandat.sepia.data.FakeBookFileStore
import io.github.trinhvandat.sepia.data.ImportBookUseCase
import io.github.trinhvandat.sepia.data.InMemoryBookRepository
import io.github.trinhvandat.sepia.data.TestEpub
import io.github.trinhvandat.sepia.domain.Book
import io.github.trinhvandat.sepia.domain.BookSource
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class ContentPackSyncerTest {
    private val manifest = ContentPackManifest(
        books = listOf(
            ContentPackBook("sepia:a", "A", file = "a.epub", sha256 = "sha-a", pipelineVersion = 8),
            ContentPackBook("sepia:b", "B", file = "b.epub", sha256 = "sha-b", pipelineVersion = 8),
        ),
    )

    /** Dựng sẵn một cuốn trong repo in-memory (giống sách đã nhập từ lần sync trước). */
    private suspend fun InMemoryBookRepository.seed(bookUid: String, contentHash: String, pipelineVersion: Int) {
        insert(
            Book(
                id = "id-$bookUid",
                bookUid = bookUid,
                title = "Seed",
                author = "",
                filePath = "/fake/$bookUid.epub",
                contentHash = contentHash,
                pipelineVersion = pipelineVersion,
                source = BookSource.Pack,
                addedAt = 0L,
                sortIndex = 0,
            ),
        )
    }

    /** ContentPackSource giả: trả manifest cố định + bytes EPUB thật dựng từ TestEpub cho mỗi entry. */
    private class FakeSource(
        private val manifest: ContentPackManifest,
        private val failFiles: Set<String> = emptySet(),
    ) : ContentPackSource {
        override suspend fun readManifest(): ContentPackManifest = manifest

        override suspend fun readEpub(file: String): ByteArray? {
            if (file in failFiles) throw IllegalStateException("boom: $file")
            val entry = manifest.books.first { it.file == file }
            return TestEpub.bytes(
                identifier = entry.bookUid,
                title = entry.title,
                pipelineVersion = entry.pipelineVersion,
                sourcePdf = entry.sourcePdfName,
            )
        }
    }

    private class FakeDeleted(private val uids: Set<String> = emptySet()) : DeletedPackStore {
        override suspend fun deletedUids(): Set<String> = uids
    }

    private fun importUseCase(repo: InMemoryBookRepository): ImportBookUseCase =
        ImportBookUseCase(repo, EpubMetadataReader(), FakeBookFileStore())

    @Test
    fun adds_new_books() = runTest {
        val repo = InMemoryBookRepository()
        val syncer = ContentPackSyncer(FakeSource(manifest), repo, importUseCase(repo), FakeDeleted())
        val r = syncer.sync()
        assertEquals(2, r.added)
        assertEquals(BookSource.Pack, repo.getByUid("sepia:a")!!.source)
    }

    @Test
    fun skips_unchanged() = runTest {
        val repo = InMemoryBookRepository()
        repo.seed("sepia:a", contentHash = "sha-a", pipelineVersion = 8)
        val syncer = ContentPackSyncer(
            FakeSource(manifest.copy(books = manifest.books.take(1))),
            repo,
            importUseCase(repo),
            FakeDeleted(),
        )
        assertEquals(ContentPackSyncReport(0, 0, 1, 0, 0), syncer.sync())
    }

    @Test
    fun replaces_on_hash_or_version_change() = runTest {
        val repo = InMemoryBookRepository()
        repo.seed("sepia:a", contentHash = "OLD", pipelineVersion = 8)
        val syncer = ContentPackSyncer(
            FakeSource(manifest.copy(books = manifest.books.take(1))),
            repo,
            importUseCase(repo),
            FakeDeleted(),
        )
        assertEquals(1, syncer.sync().replaced)
    }

    @Test
    fun never_readds_deleted() = runTest {
        val repo = InMemoryBookRepository()
        val syncer = ContentPackSyncer(
            FakeSource(manifest.copy(books = manifest.books.take(1))),
            repo,
            importUseCase(repo),
            FakeDeleted(setOf("sepia:a")),
        )
        val r = syncer.sync()
        assertEquals(0, r.added)
        assertEquals(1, r.skippedDeleted)
        assertNull(repo.getByUid("sepia:a"))
    }

    @Test
    fun null_source_is_noop() = runTest {
        val repo = InMemoryBookRepository()
        assertEquals(
            ContentPackSyncReport(0, 0, 0, 0, 0),
            ContentPackSyncer(null, repo, importUseCase(repo), FakeDeleted()).sync(),
        )
    }

    @Test
    fun one_book_failure_does_not_break_others() = runTest {
        val repo = InMemoryBookRepository()
        val src = FakeSource(manifest, failFiles = setOf("a.epub"))
        val r = ContentPackSyncer(src, repo, importUseCase(repo), FakeDeleted()).sync()
        assertEquals(1, r.added)
        assertEquals(1, r.failed)
    }
}
