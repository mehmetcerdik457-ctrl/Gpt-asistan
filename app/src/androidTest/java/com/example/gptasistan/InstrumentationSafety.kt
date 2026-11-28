package com.example.gptasistan

import android.content.Context
import android.os.Build
import java.util.Locale

/**
 * These instrumentation tests create/delete a synthetic local database.
 * Refuse to run on production package names or physical phones.
 */
internal object InstrumentationSafety {
    fun requireDisposableEmulator(context: Context) {
        val hardware = Build.HARDWARE.orEmpty().lowercase(Locale.ROOT)
        val product = Build.PRODUCT.orEmpty().lowercase(Locale.ROOT)
        val fingerprint = Build.FINGERPRINT.orEmpty().lowercase(Locale.ROOT)
        val emulator = hardware.contains("ranchu") || hardware.contains("goldfish") ||
            product.contains("sdk_gphone") || product.startsWith("sdk") ||
            fingerprint.contains("generic") || fingerprint.contains("emulator")
        check(context.packageName == "com.example.gptasistan.genesis" && emulator) {
            "DESTRUCTIVE_TEST_ONLY_ON_DISPOSABLE_DEBUG_EMULATOR"
        }
    }
}
