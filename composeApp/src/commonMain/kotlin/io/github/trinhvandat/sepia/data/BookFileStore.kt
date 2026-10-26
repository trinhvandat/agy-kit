package io.github.trinhvandat.sepia.data

/**
 * Lưu/chép file `.epub` vào vùng riêng của app (docs/04 §5). Trừu tượng hóa để import test được
 * không cần hệ thống file thật. Hiện thực Android dùng `filesDir/books`; iOS hoãn (issue #3).
 */
interface BookFileStore {
    /** Đường dẫn file `.epub` mới cho sách id này (chưa ghi). */
    fun pathForNewBook(id: String): String

    /** Ghi (đè) nội dung EPUB vào path. Ghi tạm rồi rename để an toàn khi crash giữa chừng. */
    fun writeEpub(path: String, bytes: ByteArray)

    /** Xóa file (khi xóa sách khỏi thư viện). */
    fun deleteFile(path: String)
}
