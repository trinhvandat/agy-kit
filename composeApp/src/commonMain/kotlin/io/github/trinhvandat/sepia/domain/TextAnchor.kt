package io.github.trinhvandat.sepia.domain

/**
 * Neo văn bản bền vững qua các lần build lại EPUB (docs/04 §3.1).
 * Dùng chung cho vị trí đọc (neo điểm, cfiRange độ dài 0) và Highlight (Mốc 3).
 * Renderer-agnostic: cfiRange là CFI của foliate-js (đổi sang Readium Locator nếu lật ADR-001).
 */
data class TextAnchor(
    val cfiRange: String,
    val textSnippet: String,
    val prefix: String,
    val suffix: String,
    val contentHash: String,
    val progress: Float,
)
