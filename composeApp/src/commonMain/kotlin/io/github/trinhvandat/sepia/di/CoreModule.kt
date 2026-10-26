package io.github.trinhvandat.sepia.di

import io.github.trinhvandat.sepia.data.BookRepository
import io.github.trinhvandat.sepia.data.BookRepositoryImpl
import io.github.trinhvandat.sepia.data.DatabaseDriverFactory
import io.github.trinhvandat.sepia.data.EpubMetadataReader
import io.github.trinhvandat.sepia.data.ImportBookUseCase
import io.github.trinhvandat.sepia.db.SepiaDatabase
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import org.koin.core.module.Module
import org.koin.dsl.module

/**
 * Koin module lõi (ADR-003). Phần nền tảng (DatabaseDriverFactory, BookFileStore) do module
 * androidMain/iosMain cung cấp; module này ráp phần chung dựa trên chúng.
 */
val coreModule: Module = module {
    single<CoroutineDispatcher> { Dispatchers.Default }
    // Scope cấp ứng dụng để lưu vị trí khi rời màn đọc (sống lâu hơn composable).
    single<CoroutineScope> { CoroutineScope(SupervisorJob() + get<CoroutineDispatcher>()) }
    single { SepiaDatabase(get<DatabaseDriverFactory>().createDriver()) }
    single<BookRepository> { BookRepositoryImpl(get(), get()) }
    single { EpubMetadataReader() }
    single { ImportBookUseCase(get(), get(), get()) }
}
