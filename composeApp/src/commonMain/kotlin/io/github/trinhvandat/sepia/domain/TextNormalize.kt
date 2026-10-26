package io.github.trinhvandat.sepia.domain

/** Chuẩn hóa Unicode NFC (dùng trong re-anchor, docs/04 §3.1). Hiện thực androidMain/iosMain. */
expect fun normalizeNfc(s: String): String
