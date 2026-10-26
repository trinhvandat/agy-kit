package io.github.trinhvandat.sepia.feature

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.trinhvandat.sepia.data.nowMillis
import io.github.trinhvandat.sepia.domain.AnchorText
import io.github.trinhvandat.sepia.domain.Book
import io.github.trinhvandat.sepia.reader.ReaderController
import io.github.trinhvandat.sepia.reader.ReaderEvent
import io.github.trinhvandat.sepia.reader.ReaderSurface
import io.github.trinhvandat.sepia.theme.SepiaTheme
import io.github.trinhvandat.sepia.data.BookRepository
import io.github.trinhvandat.sepia.variant.VariantConfig
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.launch
import org.koin.compose.koinInject

/**
 * Màn đọc: foliate-js (qua [ReaderSurface]) + lớp chạm Compose để lật trang (trái/phải) và
 * hiện/ẩn thanh trên (giữa). Lưu vị trí có debounce ~1s (docs/07 Mốc 2). Re-anchor khi cần (ADR-008).
 */
@OptIn(FlowPreview::class)
@Composable
fun ReaderContent(
    book: Book,
    needsReAnchor: Boolean,
    onBack: () -> Unit,
    variant: VariantConfig = VariantConfig.Default,
) {
    val repo = koinInject<BookRepository>()
    val appScope = koinInject<CoroutineScope>()
    val controller = remember(book.id) { ReaderController() }
    var uiVisible by remember { mutableStateOf(true) }
    var fontScale by remember { mutableStateOf(SepiaTheme.DefaultFontScale) }
    var failure by remember(book.id) { mutableStateOf<String?>(null) }
    var opened by remember(book.id) { mutableStateOf(false) }
    var ready by remember(book.id) { mutableStateOf(false) }
    val relocations = remember(book.id) { MutableStateFlow<ReaderEvent.Relocated?>(null) }

    val css = SepiaTheme.css(fontScale, variant.fontFallback)

    ImmersiveReaderEffect(enabled = !uiVisible)

    // Nhận sự kiện từ foliate: mở sách khi bridge sẵn sàng (idempotent), re-anchor khi cần, gom relocate.
    LaunchedEffect(controller, book.id) {
        controller.events.collect { event ->
            when (event) {
                ReaderEvent.BridgeReady -> {
                    // bridgeReady có thể đến hai lần (tự phát + ping) → chỉ mở một lần.
                    if (!opened) {
                        opened = true
                        controller.applyStyle(css)
                        val startCfi = if (needsReAnchor) null else book.positionCfi
                        controller.open(book.contentHash, startCfi)
                    }
                }
                is ReaderEvent.Ready -> {
                    ready = true
                    if (needsReAnchor) book.readingAnchor()?.let { a ->
                        controller.reAnchor("pos", AnchorText.fullQuery(a), AnchorText.snippetQuery(a), a.progress)
                    }
                }
                is ReaderEvent.Relocated -> relocations.value = event
                is ReaderEvent.ReanchorResult -> {
                    val cfi = event.cfis.firstOrNull()
                    if (cfi != null) controller.goTo(cfi) else controller.goToFraction(book.progress)
                }
                is ReaderEvent.Failure -> failure = "${event.where}: ${event.message}"
            }
        }
    }

    // Quá ~5s sau khi mở mà chưa 'ready' → báo lỗi thay vì màn trống (docs/07 Mốc 2, review #2).
    LaunchedEffect(opened) {
        if (opened) {
            kotlinx.coroutines.delay(5000)
            if (!ready && failure == null) {
                failure = "Quá hạn mở sách: foliate-js không phản hồi (xem logcat/chrome://inspect)"
            }
        }
    }

    // Đổi cỡ chữ → tiêm lại CSS (chỉ sau khi bridge sẵn sàng; tránh gọi window.sepia khi chưa định nghĩa).
    LaunchedEffect(css, opened) { if (opened) controller.applyStyle(css) }

    // Lưu vị trí có debounce (docs/04 §2: positionCfi + snippet/prefix/suffix + progress).
    LaunchedEffect(book.id) {
        relocations.filterNotNull().debounce(1000).collect { r ->
            repo.savePosition(
                id = book.id,
                cfi = r.cfi.ifEmpty { null },
                snippet = r.snippet.ifEmpty { null },
                prefix = r.prefix.ifEmpty { null },
                suffix = r.suffix.ifEmpty { null },
                progress = r.fraction,
                updatedAt = nowMillis(),
            )
        }
    }

    fun flushAndBack() {
        relocations.value?.let { r ->
            // lưu ngay vị trí cuối trước khi rời (debounce có thể chưa kịp chạy); appScope sống lâu hơn màn hình
            appScope.launch {
                repo.savePosition(
                    id = book.id,
                    cfi = r.cfi.ifEmpty { null },
                    snippet = r.snippet.ifEmpty { null },
                    prefix = r.prefix.ifEmpty { null },
                    suffix = r.suffix.ifEmpty { null },
                    progress = r.fraction,
                    updatedAt = nowMillis(),
                )
            }
        }
        onBack()
    }

    Box(Modifier.fillMaxSize().background(Color(SepiaTheme.BackgroundArgb))) {
        ReaderSurface(controller = controller, currentBookPath = book.filePath, modifier = Modifier.fillMaxSize())

        // Lớp chạm: 30% trái = trang trước, 40% giữa = ẩn/hiện thanh, 30% phải = trang sau.
        Row(Modifier.fillMaxSize()) {
            TapZone(0.3f) { controller.prev() }
            TapZone(0.4f) { uiVisible = !uiVisible }
            TapZone(0.3f) { controller.next() }
        }

        if (uiVisible) {
            ReaderTopBar(
                title = book.title,
                percent = book.progressPercent,
                fontScale = fontScale,
                onBack = ::flushAndBack,
                onFontDec = { fontScale = (fontScale - SepiaTheme.FontScaleStep).coerceAtLeast(SepiaTheme.MinFontScale) },
                onFontInc = { fontScale = (fontScale + SepiaTheme.FontScaleStep).coerceAtMost(SepiaTheme.MaxFontScale) },
                modifier = Modifier.align(Alignment.TopCenter),
            )
        }

        failure?.let { msg ->
            Surface(
                color = Color(0xFFB00020),
                modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth(),
            ) {
                Text("Lỗi trình đọc: $msg", color = Color.White, modifier = Modifier.padding(12.dp), fontSize = 13.sp)
            }
        }
    }
}

@Composable
private fun androidx.compose.foundation.layout.RowScope.TapZone(weight: Float, onClick: () -> Unit) {
    val interaction = remember { MutableInteractionSource() }
    Box(
        Modifier.weight(weight).fillMaxHeight()
            .clickable(interactionSource = interaction, indication = null, onClick = onClick),
    )
}

@Composable
private fun ReaderTopBar(
    title: String,
    percent: Int,
    fontScale: Int,
    onBack: () -> Unit,
    onFontDec: () -> Unit,
    onFontInc: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(color = Color(0xF2F2E7D0), modifier = modifier.fillMaxWidth()) {
        Row(
            Modifier.statusBarsPadding().fillMaxWidth().padding(horizontal = 8.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TextButton(onClick = onBack) { Text("‹ Thư viện") }
            Text(
                title,
                modifier = Modifier.weight(1f).padding(horizontal = 4.dp),
                color = Color(SepiaTheme.ForegroundArgb),
                fontWeight = FontWeight.Medium,
                maxLines = 1,
                fontSize = 15.sp,
            )
            Text("$percent%", color = Color(SepiaTheme.ForegroundArgb), fontSize = 13.sp)
            TextButton(onClick = onFontDec) { Text("A−", fontSize = 16.sp) }
            TextButton(onClick = onFontInc) { Text("A+", fontSize = 18.sp) }
        }
    }
}
