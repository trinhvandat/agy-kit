package io.github.trinhvandat.sepia.feature

import androidx.compose.runtime.Composable

// iOS hoãn (issue #3): UIDocumentPicker làm sau. Trả no-op để biên dịch.
@Composable
actual fun rememberEpubPicker(onPicked: (PickedEpub) -> Unit): () -> Unit = {}
