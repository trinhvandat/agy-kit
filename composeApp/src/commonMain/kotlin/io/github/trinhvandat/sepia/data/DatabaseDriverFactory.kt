package io.github.trinhvandat.sepia.data

import app.cash.sqldelight.db.SqlDriver

/** Tạo SqlDriver cho SepiaDatabase. Android cần Context; iOS dùng NativeSqliteDriver. */
expect class DatabaseDriverFactory {
    fun createDriver(): SqlDriver
}
