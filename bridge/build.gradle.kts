plugins { id("com.android.application") }

val productionOwnerSigner = "279084a36b7c17a1663bfba5fe1c5bdac974f8ef4ce56b21000d882493e39448"
val expectedOwnerSigner = System.getenv("OWNER_EXPECTED_SIGNER_SHA256") ?: productionOwnerSigner
val gitSha = System.getenv("OWNER_BUILD_GIT_SHA") ?: System.getenv("GITHUB_SHA") ?: "LOCAL"

android {
    namespace = "com.mehmetcerdik.ownerbridge"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.mehmetcerdik.ownerbridge"
        minSdk = 26
        targetSdk = 35
        versionCode = 4
        versionName = "1.2.1"
        buildConfigField("String", "EXPECTED_CORE_SIGNER_SHA256", "\"$expectedOwnerSigner\"")
        buildConfigField("String", "BUILD_GIT_SHA", "\"$gitSha\"")
    }
    buildFeatures { buildConfig = true }
    buildTypes {
        release { isDebuggable = false; isMinifyEnabled = false; signingConfig = null }
        debug { isDebuggable = true }
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
}
