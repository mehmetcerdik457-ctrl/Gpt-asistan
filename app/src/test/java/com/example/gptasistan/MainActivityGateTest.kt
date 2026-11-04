package com.example.gptasistan

import android.app.Activity
import android.app.KeyguardManager
import android.content.Context
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.shadows.ShadowDialog

/** Lock-screen regressions use no private database, network, SMTP or device credential success. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class MainActivityGateTest {
    @Test fun emailVerificationRequiresDeviceCredentialAndDoesNotReplaceGateway() {
        val controller = Robolectric.buildActivity(MainActivity::class.java).create().start().resume().visible()
        val activity = controller.get()
        val preferences = activity.getSharedPreferences("kral_model", Context.MODE_PRIVATE)
        preferences.edit().clear().putString("endpoint", "https://gateway.example").commit()
        val keyguard = activity.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
        shadowOf(keyguard).setIsDeviceSecure(true)
        try {
            activity.confirmVerifiedEmail("https://untrusted.example", "user@example.com")
            val credential = shadowOf(activity).nextStartedActivityForResult
            assertNotNull(credential)
            assertEquals(4701, credential.requestCode)
            assertTrue(allText(activity.window.decorView).contains("Kilidi aç"))
            assertEquals("https://gateway.example", preferences.getString("endpoint", ""))
            assertFalse(preferences.contains("otp_endpoint"))
            shadowOf(activity).receiveResult(credential.intent, Activity.RESULT_CANCELED, null)
            assertTrue(allText(activity.window.decorView).contains("Kilidi aç"))
            assertEquals("https://gateway.example", preferences.getString("endpoint", ""))
        } finally { controller.pause().stop().destroy(); preferences.edit().clear().commit() }
    }

    @Test fun mailboxVerificationCannotOpenHistoryOnDeviceWithoutSecureLock() {
        val controller = Robolectric.buildActivity(MainActivity::class.java).create().start().resume().visible()
        val activity = controller.get()
        val keyguard = activity.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
        shadowOf(keyguard).setIsDeviceSecure(false)
        try {
            activity.confirmVerifiedEmail("https://mail.example", "user@example.com")
            assertNull(shadowOf(activity).nextStartedActivityForResult)
            assertTrue(allText(activity.window.decorView).contains("Kilidi aç"))
            val dialog = ShadowDialog.getLatestDialog()
            assertTrue(dialog.isShowing)
            assertTrue(allText(dialog.window!!.decorView).contains("güvenli ekran kilidi"))
        } finally { controller.pause().stop().destroy() }
    }

    @Test fun backgroundVerificationIsIgnoredAndDialogsDismissBeforeRelock() {
        val controller = Robolectric.buildActivity(MainActivity::class.java).create().start().resume().visible()
        val activity = controller.get()
        try {
            allViews(activity.window.decorView).filterIsInstance<Button>()
                .single { it.text.toString() == "E-posta ile doğrula" }.performClick()
            val dialog = ShadowDialog.getLatestDialog()
            assertTrue(dialog.isShowing)
            controller.pause().stop()
            assertFalse(dialog.isShowing)
            activity.confirmVerifiedEmail("https://mail.example", "user@example.com")
            assertNull(shadowOf(activity).nextStartedActivityForResult)
            controller.start().resume().visible()
            assertTrue(allText(activity.window.decorView).contains("Kilidi aç"))
        } finally { controller.pause().stop().destroy() }
    }

    @Test fun emailFormKeepsItsEndpointSeparateFromConfiguredModelGateway() {
        val controller = Robolectric.buildActivity(MainActivity::class.java).create().start().resume().visible()
        val activity = controller.get()
        val preferences = activity.getSharedPreferences("kral_model", Context.MODE_PRIVATE)
        preferences.edit().clear().putString("endpoint", "https://gateway.example")
            .putString("otp_endpoint", "https://mail.example").commit()
        try {
            allViews(activity.window.decorView).filterIsInstance<Button>()
                .single { it.text.toString() == "E-posta ile doğrula" }.performClick()
            val inputs = allViews(ShadowDialog.getLatestDialog().window!!.decorView).filterIsInstance<EditText>()
            assertEquals("https://mail.example", inputs.first().text.toString())
            assertEquals("https://gateway.example", preferences.getString("endpoint", ""))
        } finally { controller.pause().stop().destroy(); preferences.edit().clear().commit() }
    }

    private fun allViews(view: View): List<View> = listOf(view) + if (view is ViewGroup)
        (0 until view.childCount).flatMap { allViews(view.getChildAt(it)) } else emptyList()

    private fun allText(view: View) = allViews(view).filterIsInstance<TextView>().joinToString(" ") { it.text }
}
