package io.github.trinhvandat.sepia.domain

/** Nguồn gốc của một cuốn sách: người dùng tự nhập, hay kèm sẵn trong APK (content pack). */
enum class BookSource(val wire: String) {
    Import("import"),
    Pack("pack"),
    ;

    companion object {
        fun fromWire(s: String?) = entries.firstOrNull { it.wire == s } ?: Import
    }
}
