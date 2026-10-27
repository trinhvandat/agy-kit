package io.github.trinhvandat.sepia

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.Color
import io.github.trinhvandat.sepia.content.ContentPackSyncer
import io.github.trinhvandat.sepia.data.BookRepository
import io.github.trinhvandat.sepia.data.ImportBookUseCase
import io.github.trinhvandat.sepia.domain.ImportOutcome
import io.github.trinhvandat.sepia.feature.LibraryContent
import io.github.trinhvandat.sepia.feature.ReaderContent
import io.github.trinhvandat.sepia.feature.rememberEpubPicker
import io.github.trinhvandat.sepia.theme.SepiaTheme
import io.github.trinhvandat.sepia.variant.VariantConfig
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import org.koin.compose.KoinContext
import org.koin.compose.koinInject

private val SepiaColors = lightColorScheme(
    background = Color(SepiaTheme.BackgroundArgb),
    surface = Color(SepiaTheme.BackgroundArgb),
    onBackground = Color(SepiaTheme.ForegroundArgb),
    onSurface = Color(SepiaTheme.ForegroundArgb),
    primary = Color(SepiaTheme.ForegroundArgb),
)

/**
 * Gốc app: thư viện ↔ màn đọc (điều hướng bằng state, chưa cần thư viện nav — một người, MVP).
 * Yêu cầu Koin đã khởi tạo (Android: Application.onCreate → initKoinAndroid).
 */
@Composable
fun App(variant: VariantConfig = VariantConfig.Default) {
    MaterialTheme(colorScheme = SepiaColors) {
        KoinContext {
            val repo = koinInject<BookRepository>()
            val importer = koinInject<ImportBookUseCase>()
            val scope = rememberCoroutineScope()
            val syncer = koinInject<ContentPackSyncer>()
            val appScope = koinInject<CoroutineScope>()

            LaunchedEffect(Unit) {
                appScope.launch {
                    try {
                        val report = syncer.sync()
                        println("[ContentPack] sync: $report")
                    } catch (e: kotlinx.coroutines.CancellationException) {
                        throw e
                    } catch (e: Throwable) {
                        println("[ContentPack] sync failed: $e")
                    }
                }
            }

            val books by repo.observeBooks().collectAsState(initial = emptyList())
            var openId by remember { mutableStateOf<String?>(null) }
            var reAnchorId by remember { mutableStateOf<String?>(null) }
            var status by remember { mutableStateOf<String?>(null) }

            val pickEpub = rememberEpubPicker { picked ->
                scope.launch {
                    val fallback = picked.displayName.removeSuffix(".epub")
                    status = when (val outcome = importer.import(picked.bytes, fallback)) {
                        is ImportOutcome.Created ->
                            if (outcome.external) "Đã thêm sách ngoài (không re-anchor xuyên bản build)"
                            else "Đã thêm \"${outcome.book.title}\""
                        is ImportOutcome.Replaced -> {
                            if (outcome.contentChanged && outcome.book.positionSnippet != null) {
                                reAnchorId = outcome.book.id
                            }
                            if (outcome.contentChanged) "Đã cập nhật \"${outcome.book.title}\" — sẽ định vị lại vị trí đọc"
                            else "Sách không đổi"
                        }
                    }
                }
            }

            val current = openId?.let { id -> books.firstOrNull { it.id == id } }
            if (current == null) {
                LibraryContent(
                    books = books,
                    onAdd = pickEpub,
                    onOpen = { openId = it.id },
                    onDelete = { book -> appScope.launch { repo.delete(book) } },
                    status = status,
                    onStatusShown = { status = null },
                )
            } else {
                ReaderContent(
                    book = current,
                    needsReAnchor = reAnchorId == current.id,
                    onBack = { openId = null; reAnchorId = null },
                    variant = variant,
                )
            }
        }
    }
}
