plugins { id("com.android.application"); kotlin("android") }
android {
  namespace = "com.example.gptasistan"
  compileSdk = 34
  defaultConfig {
    applicationId = "com.example.gptasistan"
    minSdk = 24
    targetSdk = 34
    versionCode = 1
    versionName = "1.0.0"
  }
  buildTypes {
    release { isMinifyEnabled = false; proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro") }
    debug { isDebuggable = true }
  }
}
dependencies {
  implementation("org.jetbrains.kotlin:kotlin-stdlib:1.9.24")
  implementation("androidx.core:core-ktx:1.13.1")
  implementation("androidx.appcompat:appcompat:1.7.0")
  implementation("com.google.android.material:material:1.12.0")
}
