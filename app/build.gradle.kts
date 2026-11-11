plugins { id("com.android.application"); kotlin("android") }

android {
    namespace = "com.example.gptasistan"
    compileSdk = 36
    defaultConfig {
        applicationId = "com.example.gptasistan.genesis"
        minSdk = 26
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        targetSdk = 36
        versionCode = 11
        versionName = "1.0.10-genesis-candidate"
        ndk { abiFilters += setOf("armeabi-v7a", "arm64-v8a", "x86", "x86_64") }
    }
    buildTypes {
        release {
            isDebuggable = false
            isMinifyEnabled = false
        }
        debug {
            isDebuggable = true
        }
    }
    // A single APK includes every supported native ABI for direct installation.
    splits { abi { isEnable = false } }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    testOptions { unitTests.isIncludeAndroidResources = true }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    implementation("org.jetbrains.kotlin:kotlin-stdlib:2.3.21")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("com.android.billingclient:billing:9.1.0")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel:2.8.4")
    implementation("androidx.lifecycle:lifecycle-livedata:2.8.4")
    implementation("com.google.android.material:material:1.12.0")
    implementation("net.zetetic:sqlcipher-android:4.19.1@aar")
    implementation("androidx.sqlite:sqlite:2.7.0")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:4.13")
    testImplementation("org.json:json:20240303")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:core:1.6.1")
}
