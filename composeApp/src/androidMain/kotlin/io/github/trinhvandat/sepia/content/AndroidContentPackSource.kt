package io.github.trinhvandat.sepia.content

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.decodeFromString

/**
 * Nguồn content pack trên Android: đọc manifest + EPUB kèm sẵn trong `assets/$assetDir`
 * (Task 8). Trả về null khi không có pack bundled — [ContentPackSyncer] sẽ no-op.
 */
class AndroidContentPackSource(
    private val context: Context,
    private val assetDir: String,
    private val json: Json = Json { ignoreUnknownKeys = true },
) : ContentPackSource {

    override suspend fun readManifest(): ContentPackManifest? = withContext(Dispatchers.IO) {
        runCatching {
            context.assets.open("$assetDir/manifest.json").use { it.readBytes() }
        }.getOrNull()?.let { bytes -> json.decodeFromString<ContentPackManifest>(bytes.decodeToString()) }
    }

    override suspend fun readEpub(file: String): ByteArray? = withContext(Dispatchers.IO) {
        runCatching {
            context.assets.open("$assetDir/$file").use { it.readBytes() }
        }.getOrNull()
    }
}
