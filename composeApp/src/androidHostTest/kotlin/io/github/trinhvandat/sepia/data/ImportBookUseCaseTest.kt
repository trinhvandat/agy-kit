package io.github.trinhvandat.sepia.data

import io.github.trinhvandat.sepia.domain.ImportOutcome
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

class ImportBookUseCaseTest {
    private fun useCase(): Triple<ImportBookUseCase, InMemoryBookRepository, FakeBookFileStore> {
        val repo = InMemoryBookRepository()
        val store = FakeBookFileStore()
        return Triple(ImportBookUseCase(repo, EpubMetadataReader(), store), repo, store)
    }

    @Test
    fun newSepiaBookIsCreated() = runTest {
        val (uc, repo, store) = useCase()
        val outcome = uc.import(TestEpub.bytes(identifier = "sepia:uid1", title = "A"), fallbackTitle = "x")
        val created = assertIs<ImportOutcome.Created>(outcome)
        assertFalse(created.external)
        assertEquals("sepia:uid1", created.book.bookUid)
        assertEquals("A", created.book.title)
        assertEquals(1, repo.observeBooks().first().size)
        assertTrue(store.written.containsKey(created.book.filePath))
    }

    @Test
    fun sameUidRebuildReplacesAndFlagsContentChanged() = runTest {
        val (uc, repo, _) = useCase()
        val first = uc.import(TestEpub.bytes(identifier = "sepia:uid1", filler = "v1"), "x")
        val firstId = first.book.id
        // Bản build lại: cùng bookUid, nội dung khác (filler) → contentHash đổi.
        val second = uc.import(TestEpub.bytes(identifier = "sepia:uid1", filler = "v2-different"), "x")
        val replaced = assertIs<ImportOutcome.Replaced>(second)
        assertTrue(replaced.contentChanged)
        assertEquals(firstId, replaced.book.id, "giữ nguyên id nội bộ (không tạo cuốn trùng)")
        assertEquals(1, repo.observeBooks().first().size, "không tạo bản ghi mới")
    }

    @Test
    fun identicalReimportReportsNoContentChange() = runTest {
        val (uc, _, _) = useCase()
        val bytes = TestEpub.bytes(identifier = "sepia:uid1", filler = "same")
        uc.import(bytes, "x")
        val second = uc.import(bytes, "x")
        val replaced = assertIs<ImportOutcome.Replaced>(second)
        assertFalse(replaced.contentChanged)
    }

    @Test
    fun positionIsPreservedAcrossRebuild() = runTest {
        val (uc, repo, _) = useCase()
        val created = uc.import(TestEpub.bytes(identifier = "sepia:uid1", filler = "v1"), "x")
        repo.savePosition(created.book.id, "epubcfi(/6/4!/2)", "đoạn văn", "trước", "sau", 0.42f, 123L)
        uc.import(TestEpub.bytes(identifier = "sepia:uid1", filler = "v2"), "x")
        val after = repo.getById(created.book.id)!!
        assertEquals("epubcfi(/6/4!/2)", after.positionCfi)
        assertEquals("đoạn văn", after.positionSnippet)
        assertEquals(0.42f, after.progress)
    }

    @Test
    fun externalEpubIsCreatedAsExternal() = runTest {
        val (uc, _, _) = useCase()
        val outcome = uc.import(TestEpub.bytes(identifier = "urn:uuid:ext", pipelineVersion = null, sourcePdf = null), "fallback")
        val created = assertIs<ImportOutcome.Created>(outcome)
        assertTrue(created.external)
        assertEquals("urn:uuid:ext", created.book.bookUid)
    }

    @Test
    fun blankTitleUsesFallback() = runTest {
        val (uc, _, _) = useCase()
        val outcome = uc.import(TestEpub.bytes(identifier = "sepia:uid1", title = ""), fallbackTitle = "Tên Tệp.epub")
        assertEquals("Tên Tệp.epub", outcome.book.title)
    }
}
