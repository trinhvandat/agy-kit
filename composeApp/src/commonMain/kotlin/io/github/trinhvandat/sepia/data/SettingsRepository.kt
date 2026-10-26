package io.github.trinhvandat.sepia.data

/**
 * Cài đặt người dùng bền vững (ADR-002 — SQLDelight key-value). Mốc 2: cỡ chữ trình đọc.
 * Sau interface để đổi engine lưu trữ về sau (giống [BookRepository]).
 */
interface SettingsRepository {
    /**
     * Cỡ chữ trình đọc theo %, đã kẹp trong `SepiaTheme.MinFontScale..MaxFontScale`.
     * Trả cỡ mặc định khi người dùng chưa đặt.
     */
    suspend fun fontScalePercent(): Int

    /** Lưu cỡ chữ (%) — tự kẹp vào khoảng hợp lệ trước khi ghi. */
    suspend fun setFontScalePercent(percent: Int)
}
