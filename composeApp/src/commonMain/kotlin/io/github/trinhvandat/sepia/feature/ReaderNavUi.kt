package io.github.trinhvandat.sepia.feature

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.trinhvandat.sepia.reader.TocFilter
import io.github.trinhvandat.sepia.reader.TocItem
import io.github.trinhvandat.sepia.theme.SepiaTheme

/**
 * Bảng **MỤC LỤC** (bottom sheet): mục đầu "Về đầu sách"; cây gập/mở theo cấp; ô TÌM (lọc bỏ dấu);
 * tự cuộn tới + tô mục đang đọc ([currentHref]). Chạm mục → [onPick] (Kotlin lo đẩy ngăn xếp + goTo).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TocBottomSheet(
    items: List<TocItem>,
    currentHref: String,
    onGoStart: () -> Unit,
    onPick: (TocItem) -> Unit,
    onDismiss: () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var query by remember { mutableStateOf("") }
    // Mở cây tới mục đang đọc (các tổ tiên của currentHref).
    var expanded by remember(items) { mutableStateOf(ancestorHrefs(items, currentHref)) }

    val filtering = query.isNotBlank()
    val shownTree = if (filtering) TocFilter.filter(items, query) else items
    val rows = remember(shownTree, expanded, filtering) { buildRows(shownTree, expanded, filtering) }

    val listState = rememberLazyListState()
    // Tự cuộn tới mục đang đọc khi KHÔNG lọc (lọc thì danh sách ngắn, để nguyên đầu).
    LaunchedEffect(rows, filtering, currentHref) {
        if (!filtering && currentHref.isNotEmpty()) {
            val idx = rows.indexOfFirst { it.item.href == currentHref }
            if (idx >= 0) listState.scrollToItem(idx)
        }
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = Color(SepiaTheme.BackgroundArgb),
    ) {
        Column(Modifier.fillMaxWidth().navigationBarsPadding()) {
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                label = { Text("Tìm trong mục lục") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
            )
            TocRow(
                label = "Về đầu sách",
                level = 0,
                selected = false,
                hasChildren = false,
                expanded = false,
                bold = true,
                onToggle = {},
                onClick = onGoStart,
            )
            HorizontalDivider(color = Color(0x22000000))
            LazyColumn(state = listState, modifier = Modifier.fillMaxWidth().heightIn(max = 480.dp)) {
                itemsIndexed(rows) { _, row ->
                    TocRow(
                        label = row.item.label,
                        level = row.item.level,
                        selected = !filtering && row.item.href == currentHref && currentHref.isNotEmpty(),
                        hasChildren = row.hasChildren,
                        expanded = row.expanded,
                        bold = row.item.level <= 1,
                        onToggle = {
                            expanded = if (row.item.href in expanded) expanded - row.item.href
                            else expanded + row.item.href
                        },
                        onClick = { onPick(row.item) },
                    )
                }
            }
        }
    }
}

/** Một dòng trong bảng mục lục: tam giác gập/mở (nếu có con) + nhãn thụt theo cấp. */
@Composable
private fun TocRow(
    label: String,
    level: Int,
    selected: Boolean,
    hasChildren: Boolean,
    expanded: Boolean,
    bold: Boolean,
    onToggle: () -> Unit,
    onClick: () -> Unit,
) {
    val indent = (8 + (level.coerceAtLeast(1) - 1) * 16).dp
    Row(
        Modifier
            .fillMaxWidth()
            .background(if (selected) Color(0x33B8860B) else Color.Transparent)
            .clickable(onClick = onClick)
            .padding(start = indent, end = 12.dp, top = 12.dp, bottom = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Box(Modifier.clip(RoundedCornerShape(4.dp)).clickable(enabled = hasChildren, onClick = onToggle)) {
            Text(
                if (hasChildren) (if (expanded) "▾" else "▸") else " ",
                color = Color(SepiaTheme.ForegroundArgb),
                fontSize = 14.sp,
                modifier = Modifier.padding(horizontal = 4.dp),
            )
        }
        Text(
            label,
            color = Color(SepiaTheme.ForegroundArgb),
            fontSize = 15.sp,
            fontWeight = if (bold || selected) FontWeight.Medium else FontWeight.Normal,
            modifier = Modifier.weight(1f),
        )
    }
}

/**
 * Thanh **TIẾN ĐỘ** ở đáy (khi thanh trên hiện). Slider 0..1 + nhãn "% · tên mục". Kéo chỉ xem trước
 * phần trăm (không nhảy liên tục); **thả tay** mới gọi [onSeek] (docs/07 Mốc 3, Việc 2).
 */
@Composable
fun BoxScope.ReaderProgressBar(
    fraction: Float,
    sectionLabel: String,
    onSeek: (Float) -> Unit,
    modifier: Modifier = Modifier,
) {
    var dragging by remember { mutableStateOf(false) }
    var dragValue by remember { mutableStateOf(fraction) }
    val shown = if (dragging) dragValue else fraction
    val percent = (shown.coerceIn(0f, 1f) * 100).toInt()
    val label = if (dragging || sectionLabel.isEmpty()) "$percent%" else "$percent% · $sectionLabel"

    Surface(color = Color(0xF2F2E7D0), modifier = modifier.fillMaxWidth()) {
        Column(Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = 16.dp, vertical = 4.dp)) {
            Text(label, color = Color(SepiaTheme.ForegroundArgb), fontSize = 12.sp, maxLines = 1)
            Slider(
                value = shown.coerceIn(0f, 1f),
                onValueChange = { dragging = true; dragValue = it },
                onValueChangeFinished = { dragging = false; onSeek(dragValue.coerceIn(0f, 1f)) },
            )
        }
    }
}

/**
 * Chip "↩ Quay lại trang trước" ở **mép dưới** (vùng Compose nhận được chạm — overlay Compose đè lên
 * *nội dung* iframe foliate thì bị iframe "nuốt" chạm, đã xác minh khi QA emulator). Chỉ hiện khi
 * **ẩn thanh** (đọc toàn màn hình); khi hiện thanh thì dùng nút "↩ Quay lại" trên thanh trên. Nút Back
 * của Android luôn quay lại (dự phòng chắc chắn). `navigationBarsPadding` để không đè thanh điều hướng.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BoxScope.BackChip(onClick: () -> Unit, modifier: Modifier = Modifier) {
    Surface(
        onClick = onClick,
        color = Color(0xF2333333),
        contentColor = Color.White,
        shape = RoundedCornerShape(20.dp),
        shadowElevation = 6.dp,
        modifier = modifier.navigationBarsPadding().padding(16.dp),
    ) {
        Text(
            "↩ Quay lại trang trước",
            fontSize = 13.sp,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
        )
    }
}

private data class VisibleRow(val item: TocItem, val hasChildren: Boolean, val expanded: Boolean)

/** Dàn cây thành danh sách dòng hiển thị: lọc → mở hết; không lọc → chỉ mở con của mục trong [expanded]. */
private fun buildRows(items: List<TocItem>, expanded: Set<String>, filtering: Boolean): List<VisibleRow> {
    val out = ArrayList<VisibleRow>()
    fun rec(list: List<TocItem>) {
        for (it in list) {
            val hasKids = it.children.isNotEmpty()
            val isExp = filtering || it.href in expanded
            out.add(VisibleRow(it, hasKids, isExp))
            if (hasKids && isExp) rec(it.children)
        }
    }
    rec(items)
    return out
}

/** Tập href của các **tổ tiên** chứa [target] (để mở sẵn cây tới mục đang đọc). */
private fun ancestorHrefs(items: List<TocItem>, target: String): Set<String> {
    if (target.isEmpty()) return emptySet()
    val acc = LinkedHashSet<String>()
    fun rec(list: List<TocItem>): Boolean {
        for (it in list) {
            if (it.href == target) return true
            if (it.children.isNotEmpty() && rec(it.children)) {
                acc.add(it.href)
                return true
            }
        }
        return false
    }
    rec(items)
    return acc
}
