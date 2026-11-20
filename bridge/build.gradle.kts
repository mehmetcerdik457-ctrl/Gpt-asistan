plugins { id("com.android.application") }

val productionOwnerSigner = "279084a36b7c17a1663bfba5fe1c5bdac974f8ef4ce56b21000d882493e39448"
val expectedOwnerSigner = System.getenv("OWNER_EXPECTED_SIGNER_SHA256") ?: productionOwnerSigner
val gitSha = System.getenv("OWNER_BUILD_GIT_SHA") ?: System.getenv("GITHUB_SHA") ?: "LOCAL"
val signingStorePath = System.getenv("ANDROID_KEYSTORE_PATH")
val signingStorePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
val signingKeyAlias = System.getenv("ANDROID_KEY_ALIAS")
val signingKeyPassword = System.getenv("ANDROID_KEY_PASSWORD")
val releaseSigningConfigured = listOf(signingStorePath, signingStorePassword, signingKeyAlias, signingKeyPassword).all { !it.isNullOrBlank() }

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
    signingConfigs {
        create("release") {
            if (releaseSigningConfigured) {
                storeFile = file(signingStorePath!!)
                storePassword = signingStorePassword
                keyAlias = signingKeyAlias
                keyPassword = signingKeyPassword
            }
        }
    }
    buildFeatures { buildConfig = true }
    buildTypes {
        release { isDebuggable = false; isMinifyEnabled = true; signingConfig = signingConfigs.getByName("release") }
        debug { isDebuggable = true }
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
}

tasks.configureEach {
    if (name == "assembleRelease" || name == "bundleRelease") {
        doFirst {
            check(releaseSigningConfigured) {
                "Release signing secrets missing: configure ANDROID_KEYSTORE_BASE64, ANDROID_KEYSTORE_PASSWORD, ANDROID_KEY_ALIAS, ANDROID_KEY_PASSWORD."
            }
            check(file(signingStorePath!!).isFile) { "ANDROID_KEYSTORE_PATH does not point to a keystore file." }
        }
    }
}
