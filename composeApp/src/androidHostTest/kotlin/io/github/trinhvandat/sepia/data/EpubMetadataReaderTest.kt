package io.github.trinhvandat.sepia.data

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class EpubMetadataReaderTest {
    private val reader = EpubMetadataReader()

    @Test
    fun docParsesSepiaMetadata() {
        val meta = reader.read(
            TestEpub.bytes(
                identifier = "sepia:abc123",
                title = "Tự Học Đông Y",
                author = "Bùi Huy",
                pipelineVersion = 2,
                sourcePdf = "Tự Học Đông Y - Bùi Huy.pdf",
            ),
        )
        assertEquals("sepia:abc123", meta.bookUid)
        assertEquals("sepia:abc123", meta.rawIdentifier)
        assertEquals("Tự Học Đông Y", meta.title)
        assertEquals("Bùi Huy", meta.author)
        assertEquals(2, meta.pipelineVersion)
        assertEquals("Tự Học Đông Y - Bùi Huy.pdf", meta.sourcePdfName)
        assertTrue(meta.isSepiaBook)
    }

    @Test
    fun externalIdentifierIsNotSepiaBook() {
        val meta = reader.read(TestEpub.bytes(identifier = "urn:uuid:1234", pipelineVersion = null, sourcePdf = null))
        assertNull(meta.bookUid)
        assertEquals("urn:uuid:1234", meta.rawIdentifier)
        assertFalse(meta.isSepiaBook)
        assertEquals(0, meta.pipelineVersion) // thiếu meta → mặc định 0
        assertNull(meta.sourcePdfName)
        // effectiveUid dùng raw identifier khi không phải sepia
        assertEquals("urn:uuid:1234", meta.effectiveUid("hashXYZ"))
    }

    @Test
    fun missingIdentifierFallsBackToContentHash() {
        val meta = reader.read(TestEpub.bytes(identifier = null))
        assertNull(meta.rawIdentifier)
        assertEquals("sha256:HASH", meta.effectiveUid("HASH"))
    }
}
