package io.github.trinhvandat.sepia.data

import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import app.cash.sqldelight.db.SqlDriver
import io.github.trinhvandat.sepia.db.SepiaDatabase
import io.github.trinhvandat.sepia.theme.SepiaTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals

class SettingsRepositoryTest {
    private fun driver(): SqlDriver =
        JdbcSqliteDriver(JdbcSqliteDriver.IN_MEMORY).also { SepiaDatabase.Schema.create(it) }

    private fun repo(driver: SqlDriver): SettingsRepository =
        SettingsRepositoryImpl(SepiaDatabase(driver), Dispatchers.Unconfined)

    @Test
    fun defaultWhenUnset() = runTest {
        assertEquals(SepiaTheme.DefaultFontScale, repo(driver()).fontScalePercent())
    }

    @Test
    fun setAndGet() = runTest {
        val r = repo(driver())
        r.setFontScalePercent(140)
        assertEquals(140, r.fontScalePercent())
    }

    @Test
    fun coercesOutOfRange() = runTest {
        val r = repo(driver())
        r.setFontScalePercent(500)
        assertEquals(SepiaTheme.MaxFontScale, r.fontScalePercent())
        r.setFontScalePercent(5)
        assertEquals(SepiaTheme.MinFontScale, r.fontScalePercent())
    }

    @Test
    fun persistsAcrossRepoInstances() = runTest {
        val d = driver()
        repo(d).setFontScalePercent(130)
        // repo mới trên cùng driver/DB → đọc lại giá trị đã lưu (bền).
        assertEquals(130, repo(d).fontScalePercent())
    }
}
