plugins { id("com.android.application"); kotlin("android") }

val kotlinRuntimeVersion = System.getenv("KOTLIN_VERSION_OVERRIDE") ?: "2.4.20"

kotlin {
  compilerOptions {
    jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
  }
}

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
  compileOptions {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
  }
  buildTypes {
    release { isMinifyEnabled = false; proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro") }
    debug { isDebuggable = true }
  }
}
dependencies {
  implementation("org.jetbrains.kotlin:kotlin-stdlib:$kotlinRuntimeVersion")
  implementation("androidx.core:core-ktx:1.13.1")
  implementation("androidx.appcompat:appcompat:1.7.0")
  implementation("com.google.android.material:material:1.12.0")
}
