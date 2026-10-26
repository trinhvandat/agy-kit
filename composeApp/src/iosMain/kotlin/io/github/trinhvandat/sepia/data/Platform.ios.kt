package io.github.trinhvandat.sepia.data

// iOS hoãn (issue #3): nhập sách/hash chưa làm trên iOS. Stub để module biên dịch cho iosArm64/sim.
// Khi làm iOS: nowMillis = NSDate, randomUuid = NSUUID, sha256Hex = CryptoKit/CommonCrypto.

actual fun nowMillis(): Long = TODO("iOS chưa hỗ trợ (issue #3)")

actual fun randomUuid(): String = TODO("iOS chưa hỗ trợ (issue #3)")

actual fun sha256Hex(bytes: ByteArray): String = TODO("iOS chưa hỗ trợ (issue #3)")
