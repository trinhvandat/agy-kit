package io.github.trinhvandat.sepia.reader

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/**
 * Giải mã thông điệp JS→Kotlin (method + payload JSON) thành [ReaderEvent].
 *
 * Giữ thuần ở commonMain (không phụ thuộc WebView/nền tảng) để:
 *  - test parse được trên JVM (androidHostTest) không cần emulator;
 *  - dùng chung cho cả actual Android lẫn iOS sau này.
 *
 * An toàn: payload hỏng → [ReaderEvent.Failure] (không ném); method lạ → null (bỏ qua).
 */
object ReaderEventParser {
    private val json = Json { ignoreUnknownKeys = true }

    fun parse(method: String, params: String): ReaderEvent? = when (method) {
        "bridgeReady" -> ReaderEvent.BridgeReady
        "ready" -> decode<ReadyDto>(method, params) {
            ReaderEvent.Ready(it.restoredCfi.ifEmpty { null })
        }
        "relocated" -> decode<RelocatedDto>(method, params) {
            ReaderEvent.Relocated(it.cfi, it.fraction, it.snippet, it.prefix, it.suffix)
        }
        "reanchorResult" -> decode<ReanchorDto>(method, params) {
            ReaderEvent.ReanchorResult(it.token, it.cfis)
        }
        "tap" -> decode<TapDto>(method, params) { parseZone(it.zone) }
        "selection" -> decode<SelectionDto>(method, params) {
            ReaderEvent.Selection(
                cfi = it.cfi,
                text = it.text,
                prefix = it.prefix,
                suffix = it.suffix,
                fraction = it.fraction,
                rect = SelectionRect(it.rect.x, it.rect.y, it.rect.w, it.rect.h),
            )
        }
        "selectionCleared" -> ReaderEvent.SelectionCleared
        "highlightTap" -> decode<HighlightTapDto>(method, params) {
            ReaderEvent.HighlightTap(it.id, SelectionRect(it.rect.x, it.rect.y, it.rect.w, it.rect.h))
        }
        "error" -> decode<ErrorDto>(method, params) { ReaderEvent.Failure(it.where, it.message) }
        else -> null
    }

    private fun parseZone(zone: String): ReaderEvent = when (zone) {
        "left" -> ReaderEvent.Tap(TapZone.LEFT)
        "center" -> ReaderEvent.Tap(TapZone.CENTER)
        "right" -> ReaderEvent.Tap(TapZone.RIGHT)
        else -> ReaderEvent.Failure("tap", "zone không hợp lệ: $zone")
    }

    private inline fun <reified T> decode(
        method: String,
        params: String,
        map: (T) -> ReaderEvent,
    ): ReaderEvent =
        runCatching { map(json.decodeFromString<T>(params)) }
            .getOrElse { ReaderEvent.Failure(method, "payload lỗi: ${it.message}") }

    @Serializable
    private data class ReadyDto(val restoredCfi: String = "")

    @Serializable
    private data class RelocatedDto(
        val cfi: String = "",
        val fraction: Float = 0f,
        val snippet: String = "",
        val prefix: String = "",
        val suffix: String = "",
    )

    @Serializable
    private data class ReanchorDto(val token: String = "", val cfis: List<String> = emptyList())

    @Serializable
    private data class TapDto(val zone: String = "")

    @Serializable
    private data class SelectionDto(
        val cfi: String = "",
        val text: String = "",
        val prefix: String = "",
        val suffix: String = "",
        val fraction: Float = 0f,
        val rect: RectDto = RectDto(),
    )

    @Serializable
    private data class RectDto(
        val x: Float = 0f,
        val y: Float = 0f,
        val w: Float = 0f,
        val h: Float = 0f,
    )

    @Serializable
    private data class HighlightTapDto(val id: String = "", val rect: RectDto = RectDto())

    @Serializable
    private data class ErrorDto(val where: String = "", val message: String = "")
}
