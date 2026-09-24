plugins {
  id("com.android.application")
  kotlin("android")
}

val gitSha = System.getenv("OWNER_BUILD_GIT_SHA") ?: System.getenv("GITHUB_SHA") ?: "LOCAL"
val expectedSignerSha256 = "279084a36b7c17a1663bfba5fe1c5bdac974f8ef4ce56b21000d882493e39448"

android {
  namespace = "com.example.gptasistan"
  compileSdk = 35
  defaultConfig {
    applicationId = "com.mehmetcerdik.ownerai"
    minSdk = 24
    targetSdk = 35
    versionCode = 5
    versionName = "1.3.0"
    buildConfigField("String", "BUILD_GIT_SHA", "\"$gitSha\"")
    buildConfigField("String", "EXPECTED_SIGNER_SHA256", "\"$expectedSignerSha256\"")
  }
  buildFeatures { buildConfig = true }
  compileOptions {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
  }
  kotlinOptions { jvmTarget = "17" }
  buildTypes {
    release {
      isMinifyEnabled = false
      proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
    }
    debug { isDebuggable = true }
  }
}

dependencies {
  implementation("org.jetbrains.kotlin:kotlin-stdlib:1.9.24")
  implementation("androidx.core:core-ktx:1.13.1")
  implementation("androidx.appcompat:appcompat:1.7.0")
  implementation("com.google.android.material:material:1.12.0")
  testImplementation("junit:junit:4.13.2")
}
