package io.github.trinhvandat.sepia.feature

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.trinhvandat.sepia.data.nowMillis
import io.github.trinhvandat.sepia.data.randomUuid
import io.github.trinhvandat.sepia.domain.AnchorText
import io.github.trinhvandat.sepia.domain.Book
import io.github.trinhvandat.sepia.domain.Highlight
import io.github.trinhvandat.sepia.domain.HighlightStatus
import io.github.trinhvandat.sepia.reader.HighlightDraw
import io.github.trinhvandat.sepia.reader.ReaderController
import io.github.trinhvandat.sepia.reader.ReaderEvent
import io.github.trinhvandat.sepia.reader.ReaderSurface
import io.github.trinhvandat.sepia.reader.SelectionRect
import io.github.trinhvandat.sepia.reader.TapZone
import io.github.trinhvandat.sepia.theme.HighlightColor
import io.github.trinhvandat.sepia.theme.SepiaTheme
import io.github.trinhvandat.sepia.data.BookRepository
import io.github.trinhvandat.sepia.data.HighlightRepository
import io.github.trinhvandat.sepia.data.SettingsRepository
import io.github.trinhvandat.sepia.variant.VariantConfig
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.launch
import org.koin.compose.koinInject

/**
 * Màn đọc: foliate-js (qua [ReaderSurface]). Cử chỉ chạm/vuốt do **JS trong foliate** xử lý
 * (bridge.js: paginator tự vuốt lật trang; tap báo về [ReaderEvent.Tap] theo vùng 30/40/30 →
 * trái lật trước, giữa ẩn/hiện thanh, phải lật sau). KHÔNG còn lớp chạm Compose phủ WebView
 * (gỡ nợ Mốc 2 — nó nuốt nhấn-giữ chọn chữ). Lưu vị trí debounce ~1s. Re-anchor khi cần (ADR-008).
 *
 * Mốc 3b — Highlight: chọn chữ → chạm màu để tô (lưu bền + vẽ qua foliate Overlayer); chạm highlight
 * → đổi màu / Sao chép / Xoá. Chỉ vẽ highlight `active` + đúng `contentHash` (khác hash = re-anchor 3e).
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
    val settings = koinInject<SettingsRepository>()
    val highlightRepo = koinInject<HighlightRepository>()
    val appScope = koinInject<CoroutineScope>()
    val controller = remember(book.id) { ReaderController() }
    var uiVisible by remember { mutableStateOf(true) }
    // Cỡ chữ bền: nạp giá trị đã lưu khi mở; A−/A+ lưu lại ngay. Mặc định cho tới khi nạp xong.
    var fontScale by remember { mutableStateOf(SepiaTheme.DefaultFontScale) }
    var failure by remember(book.id) { mutableStateOf<String?>(null) }
    // Vùng chọn chữ hiện hành (Mốc 3a: nhận từ JS; Mốc 3b: dựng Highlight). null = không chọn.
    var selection by remember(book.id) { mutableStateOf<ReaderEvent.Selection?>(null) }
    // Highlight vừa chạm (mở thanh đổi màu/sao chép/xoá). Loại trừ lẫn nhau với `selection`.
    var tappedHighlight by remember(book.id) { mutableStateOf<ReaderEvent.HighlightTap?>(null) }
    var opened by remember(book.id) { mutableStateOf(false) }
    var ready by remember(book.id) { mutableStateOf(false) }
    val relocations = remember(book.id) { MutableStateFlow<ReaderEvent.Relocated?>(null) }

    val clipboard = LocalClipboardManager.current

    // Highlight của cuốn này; CHỈ vẽ cái active + đúng contentHash hiện hành (khác hash = re-anchor ở 3e).
    val highlights by remember(book.id) { highlightRepo.observeByBook(book.id) }
        .collectAsState(initial = emptyList())
    val drawable = remember(highlights, book.contentHash) {
        highlights
            .filter { it.status == HighlightStatus.ACTIVE && it.contentHash == book.contentHash && it.cfiRange.isNotEmpty() }
            .map { HighlightDraw(it.id, it.cfiRange, HighlightColor.fromId(it.color).cssColor) }
    }

    val css = SepiaTheme.css(fontScale, variant.fontFallback)

    // Nạp cỡ chữ đã lưu (một lần). css đổi → LaunchedEffect(css, opened) tiêm lại CSS; CFI giữ nguyên.
    LaunchedEffect(Unit) { fontScale = settings.fontScalePercent() }

    // Đổi cỡ chữ: kẹp vào khoảng hợp lệ, cập nhật UI, và LƯU bền ngay (appScope sống lâu hơn màn hình).
    fun changeFontScale(next: Int) {
        val clamped = next.coerceIn(SepiaTheme.MinFontScale, SepiaTheme.MaxFontScale)
        fontScale = clamped
        appScope.launch { settings.setFontScalePercent(clamped) }
    }

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
                is ReaderEvent.Tap -> when (event.zone) {
                    TapZone.LEFT -> controller.prev()
                    TapZone.CENTER -> uiVisible = !uiVisible
                    TapZone.RIGHT -> controller.next()
                }
                is ReaderEvent.Selection -> { selection = event; tappedHighlight = null }
                ReaderEvent.SelectionCleared -> selection = null
                is ReaderEvent.HighlightTap -> { tappedHighlight = event; selection = null }
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

    // Đẩy tập highlight xuống JS để vẽ (sau 'ready'); đổi danh sách (thêm/xoá/đổi màu) → đẩy lại.
    LaunchedEffect(drawable, ready) { if (ready) controller.setHighlights(drawable) }

    // Tạo highlight từ vùng chọn (chạm một màu). bền ngay (appScope); đóng thanh + xoá vùng chọn.
    fun createHighlight(sel: ReaderEvent.Selection, color: HighlightColor) {
        if (sel.cfi.isEmpty()) return
        val now = nowMillis()
        val h = Highlight(
            id = randomUuid(),
            bookId = book.id,
            cfiRange = sel.cfi,
            textSnippet = sel.text,
            prefix = sel.prefix,
            suffix = sel.suffix,
            contentHash = book.contentHash,
            color = color.id,
            progress = sel.fraction,
            createdAt = now,
            updatedAt = now,
        )
        appScope.launch { highlightRepo.insert(h) }
        controller.clearSelection()
        selection = null
    }

    fun changeHighlightColor(id: String, color: HighlightColor) {
        appScope.launch { highlightRepo.updateColor(id, color.id, nowMillis()) }
        tappedHighlight = null
    }

    fun deleteHighlight(id: String) {
        appScope.launch { highlightRepo.delete(id) }
        controller.removeHighlight(id)
        tappedHighlight = null
    }

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

    BoxWithConstraints(Modifier.fillMaxSize().background(Color(SepiaTheme.BackgroundArgb))) {
        val screenW = maxWidth
        val screenH = maxHeight
        ReaderSurface(controller = controller, currentBookPath = book.filePath, modifier = Modifier.fillMaxSize())

        // Không còn lớp chạm Compose: cử chỉ do JS trong foliate xử lý (vuốt = paginator; tap = event.Tap).

        if (uiVisible) {
            ReaderTopBar(
                title = book.title,
                percent = book.progressPercent,
                fontScale = fontScale,
                onBack = ::flushAndBack,
                onFontDec = { changeFontScale(fontScale - SepiaTheme.FontScaleStep) },
                onFontInc = { changeFontScale(fontScale + SepiaTheme.FontScaleStep) },
                modifier = Modifier.align(Alignment.TopCenter),
            )
        }

        // Thanh chọn chữ (thay ActionMode hệ thống — đã chặn ở WebView): chấm màu tạo highlight,
        // Sao chép, Bỏ chọn. Đặt cạnh vùng chọn, kẹp trong màn hình.
        selection?.let { sel ->
            FloatingActionBar(rect = sel.rect, screenW = screenW, screenH = screenH) {
                ColorDots(onPick = { createHighlight(sel, it) })
                BarButton("Sao chép") {
                    clipboard.setText(AnnotatedString(sel.text))
                    controller.clearSelection()
                    selection = null
                }
                BarButton("Bỏ chọn") {
                    controller.clearSelection()
                    selection = null
                }
            }
        }

        // Thanh khi chạm một highlight: đổi màu, Sao chép, Xoá.
        val tapped = tappedHighlight
        val tappedData = tapped?.let { t -> highlights.firstOrNull { it.id == t.id } }
        if (tapped != null && tappedData != null) {
            FloatingActionBar(rect = tapped.rect, screenW = screenW, screenH = screenH) {
                ColorDots(
                    selected = HighlightColor.fromId(tappedData.color),
                    onPick = { changeHighlightColor(tapped.id, it) },
                )
                BarButton("Sao chép") {
                    clipboard.setText(AnnotatedString(tappedData.textSnippet))
                    tappedHighlight = null
                }
                BarButton("Xoá") { deleteHighlight(tapped.id) }
            }
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

/**
 * Thanh nổi cạnh vùng chọn/ highlight (`rect` theo CSS px của WebView ≈ dp). Đo kích thước thật
 * ([onSizeChanged]) rồi KẸP trong màn hình: tràn phải → dời sang trái; sát đáy → đặt TRÊN vùng chọn.
 */
@Composable
private fun FloatingActionBar(
    rect: SelectionRect,
    screenW: Dp,
    screenH: Dp,
    content: @Composable () -> Unit,
) {
    val density = LocalDensity.current
    var size by remember { mutableStateOf(IntSize.Zero) }
    val margin = 8.dp
    val barW = with(density) { size.width.toDp() }
    val barH = with(density) { size.height.toDp() }

    val maxX = (screenW - barW - margin).coerceAtLeast(margin)
    val x = rect.x.dp.coerceIn(margin, maxX)

    val below = (rect.y + rect.h + 4f).dp
    val above = (rect.y - 4f).dp - barH
    val maxY = (screenH - barH - margin).coerceAtLeast(margin)
    val y = if (below > maxY && above >= margin) above else below.coerceIn(margin, maxY)

    Surface(
        color = Color(0xF2F2E7D0),
        shadowElevation = 4.dp,
        modifier = Modifier.offset(x = x, y = y).onSizeChanged { size = it },
    ) {
        Row(
            Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            content()
        }
    }
}

/** Dãy chấm màu highlight (bảng màu lõi). [selected] được viền để biết màu hiện tại. */
@Composable
private fun ColorDots(selected: HighlightColor? = null, onPick: (HighlightColor) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
        for (c in HighlightColor.entries) {
            val isSel = c == selected
            Box(
                Modifier
                    .size(24.dp)
                    .clip(CircleShape)
                    .background(Color(c.argb))
                    .border(if (isSel) 2.dp else 1.dp, if (isSel) Color(SepiaTheme.ForegroundArgb) else Color(0x33000000), CircleShape)
                    .clickable { onPick(c) },
            )
        }
    }
}

@Composable
private fun BarButton(label: String, onClick: () -> Unit) {
    TextButton(onClick = onClick, contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp)) {
        Text(label, fontSize = 13.sp)
    }
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
