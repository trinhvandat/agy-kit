package io.github.trinhvandat.sepia.domain

import java.text.Normalizer

actual fun normalizeNfc(s: String): String = Normalizer.normalize(s, Normalizer.Form.NFC)
