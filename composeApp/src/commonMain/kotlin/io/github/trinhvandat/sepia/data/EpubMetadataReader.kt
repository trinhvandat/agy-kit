package io.github.trinhvandat.sepia.data

import io.github.trinhvandat.sepia.domain.EpubMetadata

/**
 * Đọc metadata từ file EPUB (OPF): dc:identifier/title/creator + meta sepia:*.
 * Hiện thực Android dùng java.util.zip + parser XML của JDK; iOS hoãn (issue #3).
 */
expect class EpubMetadataReader() {
    /** @param epubBytes toàn bộ nội dung file `.epub`. @throws nếu không phải EPUB hợp lệ. */
    fun read(epubBytes: ByteArray): EpubMetadata
}
