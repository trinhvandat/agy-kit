package io.github.trinhvandat.sepia.di

import io.github.trinhvandat.sepia.data.AndroidBookFileStore
import io.github.trinhvandat.sepia.data.BookFileStore
import io.github.trinhvandat.sepia.data.DatabaseDriverFactory
import org.koin.android.ext.koin.androidContext
import org.koin.core.module.Module
import org.koin.dsl.module

/** Phần nền tảng Android cho Koin: driver DB + nơi lưu file. Ráp cùng [coreModule]. */
val androidModule: Module = module {
    single { DatabaseDriverFactory(androidContext()) }
    single<BookFileStore> { AndroidBookFileStore(androidContext()) }
}
