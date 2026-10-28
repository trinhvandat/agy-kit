package io.github.trinhvandat.sepia.reader

import io.github.trinhvandat.sepia.domain.AnchorSimilarity

/**
 * Một mục trong **mục lục** (dựng từ `view.book.toc` của foliate). [level] bắt đầu từ 1 (cấp cao
 * nhất). [children] là các mục con (foliate `subitems`). Thuần commonMain → test không cần WebView.
 */
data class TocItem(
    val label: String,
    val href: String,
    val level: Int,
    val children: List<TocItem> = emptyList(),
)

/**
 * Lọc cây mục lục theo chữ gõ vào ô TÌM — **bỏ dấu** và **không phân biệt hoa/thường** (dùng
 * [AnchorSimilarity.stripDiacritics] để "giac hoi" khớp "Giác hơi"). Giữ một mục nếu nhãn của nó
 * khớp HOẶC có con cháu khớp (không mất ngữ cảnh cây). Mục tự khớp → giữ nguyên cả cây con.
 */
object TocFilter {
    private val whitespace = Regex("\\s+")

    private fun canon(s: String): String =
        AnchorSimilarity.stripDiacritics(s).lowercase().replace(whitespace, " ").trim()

    fun filter(items: List<TocItem>, query: String): List<TocItem> {
        val q = canon(query)
        if (q.isEmpty()) return items
        return items.mapNotNull { item ->
            if (canon(item.label).contains(q)) {
                item
            } else {
                val kids = filter(item.children, q)
                if (kids.isNotEmpty()) item.copy(children = kids) else null
            }
        }
    }
}
