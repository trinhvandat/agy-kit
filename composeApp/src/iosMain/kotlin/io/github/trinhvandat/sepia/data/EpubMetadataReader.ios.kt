package io.github.trinhvandat.sepia.data

import io.github.trinhvandat.sepia.domain.EpubMetadata

// iOS hoãn (issue #3): nhập EPUB trên iOS chưa làm. Stub giữ module biên dịch cho iOS.
actual class EpubMetadataReader actual constructor() {
    actual fun read(epubBytes: ByteArray): EpubMetadata = TODO("iOS chưa hỗ trợ (issue #3)")
}
