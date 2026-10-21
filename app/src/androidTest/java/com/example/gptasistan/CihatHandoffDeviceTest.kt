package com.example.gptasistan

import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Real Android emulator negative-path acceptance only.
 *
 * The fresh CI emulator does NOT contain the third-party CİHAT APK.
 * These tests must never be described as CİHAT live messaging tests.
 */
@RunWith(AndroidJUnit4::class)
class CihatHandoffDeviceTest {
    @Test fun absentCihatPackageFailsVerifiedIdentityGate() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val check = CihatIdentity.inspect(context)
        assertFalse(check.verified)
        assertTrue(check.state == CihatIdentity.State.NOT_INSTALLED ||
            check.state == CihatIdentity.State.UNAVAILABLE)
    }

    @Test fun absentCihatPackageDoesNotProduceAnImplicitLaunchIntent() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        // Failure to install the proprietary app is expected on a clean emulator.
        assertNull(context.packageManager.getLaunchIntentForPackage(CihatHandoff.PACKAGE_NAME))
    }

    @Test fun ownerLockDoesNotOfferHandoffBeforeCredentialVerification() {
        val scenario = ActivityScenario.launch(MainActivity::class.java)
        try {
            scenario.onActivity { activity ->
                val text = allVisibleText(activity.window.decorView)
                assertTrue(text.contains("Kilidi aç"))
                assertFalse(text.contains("CİHAT AI'ı aç (mevcut uygulama)"))
                assertFalse(text.contains("Metni kopyala ve aç"))
                assertFalse(text.contains("CİHAT yanıtını panodan al (önizleme)"))
                assertFalse(text.contains("CİHAT kurulumunu doğrula (salt okunur)"))
            }
        } finally {
            scenario.close()
        }
    }

    private fun allVisibleText(view: View): String {
        if (view.visibility != View.VISIBLE) return ""
        return when (view) {
            is TextView -> view.text.toString()
            is ViewGroup -> (0 until view.childCount)
                .joinToString(" ") { allVisibleText(view.getChildAt(it)) }
            else -> ""
        }
    }
}
