import java.util.Properties
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

// Ký APK release: đọc từ keystore.properties (dev cục bộ, gitignored) hoặc biến môi trường (CI
// release.yml). Thiếu cả hai → KHÔNG cấu hình ký: assembleRelease ra APK CHƯA ký, còn
// assembleDebug/test không cần key → job test CI vẫn chạy không cần secret. Xem .omc/RELEASE_RULE.md.
val keystorePropsFile = rootProject.file("keystore.properties")
val keystoreProps = Properties().apply {
    if (keystorePropsFile.exists()) keystorePropsFile.inputStream().use { load(it) }
}
fun signingSecret(propKey: String, envKey: String): String? =
    (keystoreProps.getProperty(propKey) ?: System.getenv(envKey))?.takeIf { it.isNotBlank() }
val releaseStorePath = signingSecret("storeFile", "RELEASE_KEYSTORE_PATH")

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

    signingConfigs {
        create("release") {
            if (releaseStorePath != null) {
                storeFile = file(releaseStorePath)
                storePassword = signingSecret("storePassword", "RELEASE_STORE_PASSWORD")
                keyAlias = signingSecret("keyAlias", "RELEASE_KEY_ALIAS")
                keyPassword = signingSecret("keyPassword", "RELEASE_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        getByName("release") {
            // R8/shrink TẮT cho v0.1.0 — foliate/WebView dùng reflection, bật minify dễ vỡ; để sau
            // khi có thời gian viết proguard-rules. debuggable=false (mặc định) → tắt __sepiaPerf +
            // WebView debugging (gated theo FLAG_DEBUGGABLE ở ReaderSurface.android.kt).
            isMinifyEnabled = false
            // Chỉ gắn ký khi có keystore (local hoặc CI); không có thì để APK chưa ký.
            if (releaseStorePath != null) signingConfig = signingConfigs.getByName("release")
        }
    }
}

// sepia.contentDir: when set (-Psepia.contentDir=<dir> or gradle.properties) and the dir exists,
// sync its contents into a generated assets dir under build/ and register that dir as an
// additional assets srcDir. srcDir must be the dir that CONTAINS `content/`, so the final APK
// path resolves to assets/content/... (matches AndroidContentPackSource's "content/manifest.json").
val contentDir = (project.findProperty("sepia.contentDir") as String?)?.takeIf { it.isNotBlank() }
val generatedContentAssets = layout.buildDirectory.dir("generated/contentAssets")

val syncContentPack = tasks.register<Sync>("syncContentPack") {
    val dest = generatedContentAssets.get().dir("content")
    if (contentDir != null && file(contentDir).isDirectory) {
        from(contentDir)
    }
    into(dest)
}

android {
    sourceSets.getByName("main").assets.srcDir(generatedContentAssets.get().asFile)
}

tasks.named("preBuild") { dependsOn(syncContentPack) }
