package io.github.trinhvandat.sepia.data

import android.content.Context
import androidx.sqlite.db.SupportSQLiteDatabase
import app.cash.sqldelight.db.SqlDriver
import app.cash.sqldelight.driver.android.AndroidSqliteDriver
import io.github.trinhvandat.sepia.db.SepiaDatabase

actual class DatabaseDriverFactory(private val context: Context) {
    actual fun createDriver(): SqlDriver =
        AndroidSqliteDriver(
            schema = SepiaDatabase.Schema,
            context = context,
            name = "sepia.db",
            // Bật FK để Highlight.bookId ON DELETE CASCADE chạy (SQLite mặc định tắt mỗi kết nối).
            callback = object : AndroidSqliteDriver.Callback(SepiaDatabase.Schema) {
                override fun onConfigure(db: SupportSQLiteDatabase) {
                    super.onConfigure(db)
                    db.setForeignKeyConstraintsEnabled(true)
                }
            },
        )
}
