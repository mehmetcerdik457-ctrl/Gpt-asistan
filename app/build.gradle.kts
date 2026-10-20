plugins { id("com.android.application"); kotlin("android") }

android {
    namespace = "com.example.gptasistan"
    compileSdk = 34
    defaultConfig {
        applicationId = "com.example.gptasistan"
        minSdk = 26
        targetSdk = 34
        versionCode = 2
        versionName = "1.0.1-kral-integration"
    }
    buildTypes {
        release {
            isMinifyEnabled = false
        }
        debug { isDebuggable = true }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}
dependencies {
    implementation("org.jetbrains.kotlin:kotlin-stdlib:1.9.24")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    testImplementation("junit:junit:4.13.2")
}
