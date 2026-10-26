package io.github.trinhvandat.sepia.feature

import androidx.compose.runtime.Composable

/** Một file EPUB người dùng chọn qua SAF/UIDocumentPicker. */
class PickedEpub(val bytes: ByteArray, val displayName: String)

/**
 * Trả lambda để mở bộ chọn file EPUB (SAF Android `ACTION_OPEN_DOCUMENT`, mime application/epub+zip).
 * iOS: hoãn (issue #3). [onPicked] gọi trên main sau khi đã đọc xong bytes.
 */
@Composable
expect fun rememberEpubPicker(onPicked: (PickedEpub) -> Unit): () -> Unit
