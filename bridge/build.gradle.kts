plugins { id("com.android.application") }
android {
    namespace = "com.mehmetcerdik.ownerbridge"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.mehmetcerdik.ownerbridge"
        minSdk = 26
        targetSdk = 35
        versionCode = 2
        versionName = "1.1.0"
    }
    buildTypes { getByName("release") { isMinifyEnabled = false; signingConfig = null } }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
}