package io.github.trinhvandat.sepia

import android.app.Application
import io.github.trinhvandat.sepia.di.initKoinAndroid

/** Application mỏng: khởi tạo Koin (coreModule + androidModule) một lần khi app khởi động. */
class SepiaApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        initKoinAndroid(this)
    }
}
