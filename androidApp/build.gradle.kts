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
