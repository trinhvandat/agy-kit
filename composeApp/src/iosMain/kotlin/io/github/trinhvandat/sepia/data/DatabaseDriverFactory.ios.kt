package io.github.trinhvandat.sepia.data

import app.cash.sqldelight.db.SqlDriver
import app.cash.sqldelight.driver.native.NativeSqliteDriver
import io.github.trinhvandat.sepia.db.SepiaDatabase

// iOS: driver native dùng được ngay; phần còn lại của iOS hoãn (issue #3).
actual class DatabaseDriverFactory {
    actual fun createDriver(): SqlDriver = NativeSqliteDriver(SepiaDatabase.Schema, "sepia.db")
}
