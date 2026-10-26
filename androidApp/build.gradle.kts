import org.jetbrains.kotlin.gradle.dsl.JvmTarget

// Module launcher Android mỏng (AGP 9 có Kotlin tích hợp sẵn) — chỉ dựng UI chung từ :composeApp.
plugins {
    alias(libs.plugins.androidApplication)
    alias(libs.plugins.composeMultiplatform)
    alias(libs.plugins.composeCompiler)
}

kotlin {
    dependencies {
        implementation(project(":composeApp"))
        implementation(libs.androidx.activity.compose)
    }
    target {
        compilerOptions {
            jvmTarget.set(JvmTarget.JVM_17)
        }
    }
}

android {
    namespace = "io.github.trinhvandat.sepia"
    compileSdk = libs.versions.compileSdk.get().toInt()

    defaultConfig {
        applicationId = "io.github.trinhvandat.sepia"
        minSdk = libs.versions.minSdk.get().toInt()
        targetSdk = libs.versions.targetSdk.get().toInt()
        versionCode = 1
        versionName = "0.1.0"
    }
}
