package io.github.trinhvandat.sepia.data

import app.cash.sqldelight.driver.jdbc.sqlite.JdbcSqliteDriver
import io.github.trinhvandat.sepia.db.SepiaDatabase
import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * Migration v2 → v3 (thêm bảng Highlight, Mốc 3b) phải GIỮ NGUYÊN Book + Setting trên máy đã cài.
 * Dựng schema v2 thủ công (Book + Setting như trước 3b), chèn dữ liệu, chạy Schema.migrate(2→3),
 * rồi kiểm dữ liệu cũ còn nguyên và bảng Highlight dùng được.
 */
class DatabaseMigrationTest {
    // DDL schema v2 (trước Mốc 3b): Book (Mốc 2) + Setting (Mốc 2, migration 1.sqm).
    private val bookDdlV2 = """
        CREATE TABLE Book (
            id TEXT NOT NULL PRIMARY KEY, bookUid TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
            author TEXT NOT NULL, filePath TEXT NOT NULL, coverPath TEXT, contentHash TEXT NOT NULL,
            pipelineVersion INTEGER NOT NULL, sourcePdfName TEXT, addedAt INTEGER NOT NULL,
            sortIndex INTEGER NOT NULL, positionCfi TEXT, positionSnippet TEXT, positionPrefix TEXT,
            positionSuffix TEXT, progress REAL NOT NULL DEFAULT 0.0, positionUpdatedAt INTEGER NOT NULL
        )
    """.trimIndent()

    @Test
    fun migrateV2ToV3KeepsBookAndSettingAndAddsHighlight() {
        val driver = JdbcSqliteDriver(JdbcSqliteDriver.IN_MEMORY)
        // --- Dựng schema v2 ---
        driver.execute(null, bookDdlV2, 0)
        driver.execute(null, "CREATE INDEX Book_sort ON Book(sortIndex, addedAt)", 0)
        driver.execute(null, "CREATE TABLE Setting (key TEXT NOT NULL PRIMARY KEY, value TEXT NOT NULL)", 0)
        // --- Dữ liệu người dùng đã có ở v2 ---
        driver.execute(
            null,
            """INSERT INTO Book(id, bookUid, title, author, filePath, contentHash, pipelineVersion,
               addedAt, sortIndex, progress, positionUpdatedAt)
               VALUES('b1','sepia:b1','Sách cũ','TG','/b/b1.epub','h1',1,100,0,0.33,100)""",
            0,
        )
        driver.execute(null, "INSERT INTO Setting(key, value) VALUES('reader.fontScalePercent','120')", 0)

        // --- Migrate v2 → v3 (chạy 2.sqm) ---
        SepiaDatabase.Schema.migrate(driver, 2L, 3L)

        val db = SepiaDatabase(driver)
        // Book còn nguyên (kể cả vị trí đọc).
        val book = db.bookQueries.selectById("b1") { id, _, title, _, _, _, _, _, _, _, _, _, _, _, _, progress, _ ->
            title to progress
        }.executeAsOne()
        assertEquals("Sách cũ", book.first)
        assertEquals(0.33, book.second)
        // Setting còn nguyên.
        assertEquals("120", db.settingsQueries.get("reader.fontScalePercent").executeAsOne())
        // Bảng Highlight mới dùng được.
        db.highlightQueries.insert(
            id = "x", bookId = "b1", kind = "highlight", cfiRange = "c", textSnippet = "t",
            prefix = "p", suffix = "s", contentHash = "h1", color = "yellow", note = null,
            status = "active", progress = 0.33, createdAt = 1, updatedAt = 1,
        )
        assertEquals(1, db.highlightQueries.selectByBook("b1") { id, _, _, _, _, _, _, _, _, _, _, _, _, _ -> id }.executeAsList().size)
    }
}
