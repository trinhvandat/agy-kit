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

    /** Hiệu ứng trượt lật trang (Trượt/Không). Mặc định bật (Trượt) khi chưa đặt. */
    suspend fun pageTurnAnimated(): Boolean

    /** Lưu lựa chọn hiệu ứng lật trang. */
    suspend fun setPageTurnAnimated(enabled: Boolean)
}
