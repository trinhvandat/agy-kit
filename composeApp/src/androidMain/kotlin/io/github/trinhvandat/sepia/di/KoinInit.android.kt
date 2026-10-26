package io.github.trinhvandat.sepia.di

import android.app.Application
import org.koin.android.ext.koin.androidContext
import org.koin.core.context.startKoin

/** Khởi tạo Koin cho Android — gọi một lần từ Application.onCreate (launcher :androidApp). */
fun initKoinAndroid(app: Application) {
    startKoin {
        androidContext(app)
        modules(coreModule, androidModule)
    }
}
