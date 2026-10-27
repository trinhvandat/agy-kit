package io.github.trinhvandat.sepia.di

import io.github.trinhvandat.sepia.content.AndroidContentPackSource
import io.github.trinhvandat.sepia.content.ContentPackSource
import io.github.trinhvandat.sepia.data.AndroidBookFileStore
import io.github.trinhvandat.sepia.data.BookFileStore
import io.github.trinhvandat.sepia.data.DatabaseDriverFactory
import io.github.trinhvandat.sepia.variant.VariantConfig
import org.koin.android.ext.koin.androidContext
import org.koin.core.module.Module
import org.koin.dsl.module

/** Phần nền tảng Android cho Koin: driver DB + nơi lưu file. Ráp cùng [coreModule]. */
val androidModule: Module = module {
    single { DatabaseDriverFactory(androidContext()) }
    single<BookFileStore> { AndroidBookFileStore(androidContext()) }
    single<ContentPackSource> {
        AndroidContentPackSource(androidContext(), get<VariantConfig>().contentPack ?: "content")
    }
}
