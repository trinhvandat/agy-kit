package io.github.trinhvandat.sepia.data

import android.content.Context
import java.io.File

/** Lưu EPUB vào `filesDir/books` (docs/04 §5). Ghi tạm rồi rename để tránh file hỏng khi crash. */
class AndroidBookFileStore(context: Context) : BookFileStore {
    private val booksDir = File(context.filesDir, "books").apply { mkdirs() }

    override fun pathForNewBook(id: String): String = File(booksDir, "$id.epub").absolutePath

    override fun writeEpub(path: String, bytes: ByteArray) {
        val target = File(path)
        target.parentFile?.mkdirs()
        val tmp = File(target.parentFile, target.name + ".tmp")
        tmp.writeBytes(bytes)
        if (target.exists()) target.delete()
        if (!tmp.renameTo(target)) {
            // Fallback nếu rename không được (hiếm): copy rồi xóa tmp.
            target.writeBytes(bytes)
            tmp.delete()
        }
    }

    override fun deleteFile(path: String) {
        File(path).delete()
    }
}
