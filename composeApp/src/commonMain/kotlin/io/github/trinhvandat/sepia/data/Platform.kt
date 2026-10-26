package io.github.trinhvandat.sepia.data

/**
 * Hàm nền tảng tối thiểu (NFR-5: danh sách actual ngắn). Hiện thực trong androidMain/iosMain.
 * iOS một số hàm còn stub — import/hash trên iOS hoãn (issue #3).
 */

/** Thời điểm hiện tại (epoch ms). */
expect fun nowMillis(): Long

/** UUID ngẫu nhiên dạng chuỗi (khóa chính Book). */
expect fun randomUuid(): String

/** SHA-256 của mảng byte → hex thường. Dùng cho contentHash file EPUB. */
expect fun sha256Hex(bytes: ByteArray): String
