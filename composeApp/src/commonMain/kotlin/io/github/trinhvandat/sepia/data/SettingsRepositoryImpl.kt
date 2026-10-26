package io.github.trinhvandat.sepia.data

import io.github.trinhvandat.sepia.db.SepiaDatabase
import io.github.trinhvandat.sepia.theme.SepiaTheme
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.withContext

/** Hiện thực [SettingsRepository] bằng bảng key-value SQLDelight. Chạy ngoài main qua [dispatcher]. */
class SettingsRepositoryImpl(
    db: SepiaDatabase,
    private val dispatcher: CoroutineDispatcher,
) : SettingsRepository {
    private val q = db.settingsQueries

    override suspend fun fontScalePercent(): Int = withContext(dispatcher) {
        q.get(KEY_FONT_SCALE).executeAsOneOrNull()?.toIntOrNull()?.let(::coerce)
            ?: SepiaTheme.DefaultFontScale
    }

    override suspend fun setFontScalePercent(percent: Int): Unit = withContext(dispatcher) {
        q.upsert(key = KEY_FONT_SCALE, value = coerce(percent).toString())
    }

    private fun coerce(p: Int) = p.coerceIn(SepiaTheme.MinFontScale, SepiaTheme.MaxFontScale)

    private companion object {
        const val KEY_FONT_SCALE = "reader.fontScalePercent"
    }
}
