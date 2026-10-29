package io.github.trinhvandat.sepia.reader

/**
 * Ngăn xếp "quay lại" cho các cú **NHẢY** trong sách (link trong sách, mục lục, thanh tiến độ,
 * "Về đầu sách") — KHÔNG dùng cho lật trang thường. Mỗi lần nhảy đẩy CFI hiện tại vào; nút Back /
 * chip "Quay lại" lấy ra đỉnh. Thuần commonMain → có unit test (docs/07 Mốc 3, PR reader-navigation).
 */
class ReaderBackStack(private val maxDepth: Int = 50) {
    private val stack = ArrayDeque<String>()

    val canGoBack: Boolean get() = stack.isNotEmpty()
    val size: Int get() = stack.size

    /**
     * Ghi vị trí (CFI) **trước** khi nhảy. Bỏ qua CFI rỗng (chưa biết vị trí) và trùng đỉnh (nhảy
     * liên tiếp từ cùng một chỗ không nên phình ngăn xếp). Vượt [maxDepth] → bỏ mục cũ nhất.
     */
    fun recordJump(fromCfi: String?) {
        val cfi = fromCfi?.takeIf { it.isNotBlank() } ?: return
        if (stack.lastOrNull() == cfi) return
        stack.addLast(cfi)
        while (stack.size > maxDepth) stack.removeFirst()
    }

    /** Lấy (và bỏ) vị trí quay lại gần nhất, hoặc null nếu ngăn xếp rỗng. */
    fun pop(): String? = if (stack.isEmpty()) null else stack.removeLast()

    fun clear() = stack.clear()
}
