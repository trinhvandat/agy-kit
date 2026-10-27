package io.github.trinhvandat.sepia.theme

/**
 * Bảng màu highlight của **lõi** — TRUNG TÍNH về lĩnh vực (US-D1), KHÔNG gắn ý nghĩa Đông y/biến thể.
 * Biến thể muốn đổi/đặt tên màu theo lĩnh vực thì làm ở lớp content/feature, không sửa đây.
 *
 * - [id]: lưu trong DB (Highlight.color) — ổn định, không đổi theo locale.
 * - [cssColor]: fill cho SVG overlay của foliate (Overlayer.highlight, opacity ~0.3) — đẩy qua bridge.
 * - [argb]: màu chấm chọn trong UI Compose (đầy đủ, 0xAARRGGBB).
 */
enum class HighlightColor(val id: String, val cssColor: String, val argb: Long) {
    YELLOW("yellow", "#F2C94C", 0xFFF2C94C),
    GREEN("green", "#7FB069", 0xFF7FB069),
    BLUE("blue", "#6FA8DC", 0xFF6FA8DC),
    PINK("pink", "#D96BA0", 0xFFD96BA0),
    ;

    companion object {
        val Default = YELLOW
        fun fromId(id: String): HighlightColor = entries.firstOrNull { it.id == id } ?: Default
    }
}
