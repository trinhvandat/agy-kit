import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.kotlinMultiplatform)
    alias(libs.plugins.androidKotlinMultiplatformLibrary)
    alias(libs.plugins.composeMultiplatform)
    alias(libs.plugins.composeCompiler)
    alias(libs.plugins.kotlinSerialization)
    alias(libs.plugins.sqldelight)
}

kotlin {
    // Android: AGP 9 → KMP là LIBRARY (AAR); module launcher :androidApp link vào.
    android {
        namespace = "io.github.trinhvandat.sepia.shared"
        compileSdk = libs.versions.compileSdk.get().toInt()
        minSdk = libs.versions.minSdk.get().toInt()
        compilerOptions {
            jvmTarget.set(JvmTarget.JVM_17)
        }
        withHostTest {}
    }

    // iOS: cùng codebase, làm sau (SPIKE-2 phần iOS). Framework tĩnh cho iosApp link vào.
    // Máy phát triển là Apple Silicon → chỉ cần iosArm64 (thiết bị) + iosSimulatorArm64 (simulator).
    listOf(
        iosArm64(),
        iosSimulatorArm64(),
    ).forEach { iosTarget ->
        iosTarget.binaries.framework {
            baseName = "ComposeApp"
            isStatic = true
        }
    }

    sourceSets {
        commonMain.dependencies {
            implementation(compose.runtime)
            implementation(compose.foundation)
            implementation(compose.material3)
            implementation(compose.ui)
            implementation(compose.components.resources)

            implementation(libs.coroutines.core)
            implementation(libs.serialization.json)

            implementation(libs.sqldelight.runtime)
            implementation(libs.sqldelight.coroutines)

            implementation(libs.koin.core)
            implementation(libs.koin.compose)

            implementation(libs.webview.multiplatform)
        }
        commonTest.dependencies {
            implementation(kotlin("test"))
            implementation(libs.coroutines.test)
        }
        androidMain.dependencies {
            implementation(libs.coroutines.android)
            implementation(libs.sqldelight.driver.android)
            implementation(libs.koin.android)
            implementation(libs.androidx.activity.compose)
        }
        // AGP 9 KMP library: test JVM nằm ở src/androidHostTest (withHostTest), chạy bằng :testAndroidHostTest.
        // Dùng driver JDBC in-memory + java.util.zip của JDK để test parse EPUB/repository.
        getByName("androidHostTest").dependencies {
            implementation(kotlin("test"))
            implementation(libs.coroutines.test)
            implementation(libs.sqldelight.driver.jvm)
        }
        iosMain.dependencies {
            implementation(libs.sqldelight.driver.native)
        }
    }
}

sqldelight {
    databases {
        create("SepiaDatabase") {
            packageName.set("io.github.trinhvandat.sepia.db")
        }
    }
}
