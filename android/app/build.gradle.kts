import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// Release signing: a keystore outside the repo. Locally ~/.orbit-keys/signing.properties
// (storeFile, storePassword, keyAlias, keyPassword); in CI the ORBIT_KEYSTORE* env vars.
// Without either, release builds fall back to the debug key (fine for local testing,
// but phones only accept updates signed with the same key, so publish with the real one).
val signingProps = Properties().apply {
    val f = file("${System.getProperty("user.home")}/.orbit-keys/signing.properties")
    if (f.exists()) f.inputStream().use { load(it) }
    System.getenv("ORBIT_KEYSTORE")?.let { setProperty("storeFile", it) }
    System.getenv("ORBIT_KEYSTORE_PASSWORD")?.let { setProperty("storePassword", it); setProperty("keyPassword", it) }
    System.getenv("ORBIT_KEY_ALIAS")?.let { setProperty("keyAlias", it) }
}
val hasReleaseKey = signingProps.getProperty("storeFile")?.let { file(it).exists() } == true

android {
    namespace = "app.orbit.dial"
    compileSdk = 36

    defaultConfig {
        applicationId = "app.orbit.dial"
        minSdk = 26
        targetSdk = 36
        versionCode = (System.getenv("ORBIT_VERSION_CODE") ?: "1").toInt()
        versionName = System.getenv("ORBIT_VERSION") ?: "0.1.1"
    }

    signingConfigs {
        if (hasReleaseKey) create("release") {
            storeFile = file(signingProps.getProperty("storeFile"))
            storePassword = signingProps.getProperty("storePassword")
            keyAlias = signingProps.getProperty("keyAlias", "orbit")
            keyPassword = signingProps.getProperty("keyPassword")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
            signingConfig = signingConfigs.getByName(if (hasReleaseKey) "release" else "debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true; buildConfig = true }
    testOptions { unitTests.isReturnDefaultValues = true }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.05.01")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.core:core-ktx:1.16.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.9.0")
    implementation("androidx.savedstate:savedstate-ktx:1.3.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.10.2")
}
