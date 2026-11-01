plugins { id("com.android.application"); kotlin("android") }

android {
    namespace = "com.example.gptasistan"
    compileSdk = 34
    defaultConfig {
        applicationId = "com.example.gptasistan"
        minSdk = 26
        targetSdk = 34
        versionCode = 4
        versionName = "1.0.3-genesis-candidate"
    }
    buildTypes {
        release {
            isMinifyEnabled = false
        }
        debug {
            isDebuggable = true
            applicationIdSuffix = ".genesis"
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    testOptions { unitTests.isIncludeAndroidResources = true }
}
dependencies {
    implementation("org.jetbrains.kotlin:kotlin-stdlib:1.9.24")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel:2.8.4")
    implementation("androidx.lifecycle:lifecycle-livedata:2.8.4")
    implementation("com.google.android.material:material:1.12.0")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:4.13")
    testImplementation("org.json:json:20240303")
}
