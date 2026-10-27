package io.github.trinhvandat.sepia.feature

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.trinhvandat.sepia.domain.Book

/** Thư viện tối giản: danh sách sách (tên, tác giả, % tiến độ), nút "Thêm sách". */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalFoundationApi::class)
@Composable
fun LibraryContent(
    books: List<Book>,
    onAdd: () -> Unit,
    onOpen: (Book) -> Unit,
    onDelete: (Book) -> Unit,
    status: String?,
    onStatusShown: () -> Unit,
) {
    val snackbar = remember { SnackbarHostState() }
    var pendingDelete by remember { mutableStateOf<Book?>(null) }
    LaunchedEffect(status) {
        if (status != null) {
            snackbar.showSnackbar(status)
            onStatusShown()
        }
    }
    Scaffold(
        topBar = { TopAppBar(title = { Text("Sepia") }) },
        snackbarHost = { SnackbarHost(snackbar) },
        floatingActionButton = {
            ExtendedFloatingActionButton(onClick = onAdd, text = { Text("Thêm sách") }, icon = {})
        },
    ) { padding ->
        if (books.isEmpty()) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Text("Chưa có sách. Bấm \"Thêm sách\" để nhập EPUB.")
            }
        } else {
            LazyColumn(Modifier.fillMaxSize().padding(padding)) {
                items(books, key = { it.id }) { book ->
                    BookRow(
                        book,
                        onClick = { onOpen(book) },
                        onLongClick = { pendingDelete = book },
                    )
                    HorizontalDivider()
                }
            }
        }
    }

    pendingDelete?.let { book ->
        AlertDialog(
            onDismissRequest = { pendingDelete = null },
            title = { Text("Xoá sách?") },
            text = { Text(book.title) },
            confirmButton = {
                TextButton(onClick = {
                    onDelete(book)
                    pendingDelete = null
                }) { Text("Xoá") }
            },
            dismissButton = {
                TextButton(onClick = { pendingDelete = null }) { Text("Huỷ") }
            },
        )
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun BookRow(book: Book, onClick: () -> Unit, onLongClick: () -> Unit) {
    Column(
        Modifier.fillMaxWidth()
            .combinedClickable(onClick = onClick, onLongClick = onLongClick)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Text(book.title, fontSize = 17.sp, fontWeight = FontWeight.Medium)
        val meta = buildString {
            if (book.author.isNotBlank()) append(book.author)
            if (book.progress > 0f) {
                if (isNotEmpty()) append(" · ")
                append("${book.progressPercent}%")
            }
        }
        if (meta.isNotEmpty()) Text(meta, fontSize = 13.sp)
    }
}
