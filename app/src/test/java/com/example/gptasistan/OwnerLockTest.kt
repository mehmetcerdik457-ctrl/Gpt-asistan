package com.example.gptasistan

import android.app.Application
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.TextView
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/** Local UI test, not physical biometric or device credential validation. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class OwnerLockTest {
    @Test fun launchDoesNotRenderSavedPrivateConversationBeforeCredentialGate() {
        val app = RuntimeEnvironment.getApplication()
        app.deleteDatabase("kral_local.db")
        val store = KralStore(app)
        try { store.saveMessage("user", "PRIVATE_TRANSCRIPT_SENTINEL") } finally { store.close() }
        val controller = Robolectric.buildActivity(MainActivity::class.java).create().start().resume().visible()
        try {
            val activity = controller.get()
            val text = allText(activity.window.decorView)
            assertTrue(text.contains("Kilidi aç"))
            assertFalse(text.contains("PRIVATE_TRANSCRIPT_SENTINEL"))
            assertEquals(WindowManager.LayoutParams.FLAG_SECURE,
                activity.window.attributes.flags and WindowManager.LayoutParams.FLAG_SECURE)
        } finally {
            controller.pause().stop().destroy()
            app.deleteDatabase("kral_local.db")
        }
    }

    private fun allText(view: View): String = when (view) {
        is TextView -> view.text.toString()
        is ViewGroup -> (0 until view.childCount).joinToString(" ") { allText(view.getChildAt(it)) }
        else -> ""
    }
}
