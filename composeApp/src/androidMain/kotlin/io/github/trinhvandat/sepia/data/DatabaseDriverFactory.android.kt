package io.github.trinhvandat.sepia.data

import android.content.Context
import app.cash.sqldelight.db.SqlDriver
import app.cash.sqldelight.driver.android.AndroidSqliteDriver
import io.github.trinhvandat.sepia.db.SepiaDatabase

actual class DatabaseDriverFactory(private val context: Context) {
    actual fun createDriver(): SqlDriver =
        AndroidSqliteDriver(SepiaDatabase.Schema, context, "sepia.db")
}
