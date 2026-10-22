package com.example.gptasistan

import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.TextView
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Android UI test; it does not dismiss or claim to validate the device credential prompt. */
@RunWith(AndroidJUnit4::class)
class OwnerLockTest {
    @Test fun launchDoesNotRenderSavedPrivateConversationBeforeCredentialGate() {
        val app = InstrumentationRegistry.getInstrumentation().targetContext.applicationContext
        app.deleteDatabase("kral_local.db")
        app.deleteDatabase("kral_local.db.plaintext-legacy")
        app.deleteDatabase("kral_local.db.cipher-staging")
        val store = KralStore(app, TestDatabaseKeyProvider)
        try { store.saveMessage("user", "PRIVATE_TRANSCRIPT_SENTINEL") } finally { store.close() }
        val scenario = ActivityScenario.launch(MainActivity::class.java)
        try {
            scenario.onActivity { activity ->
                val text = allText(activity.window.decorView)
                assertTrue(text.contains("Kilidi aç"))
                assertFalse(text.contains("PRIVATE_TRANSCRIPT_SENTINEL"))
                assertFalse(text.contains("Sesle yaz"))
                assertEquals(WindowManager.LayoutParams.FLAG_SECURE,
                    activity.window.attributes.flags and WindowManager.LayoutParams.FLAG_SECURE)
            }
        } finally {
            scenario.close()
            app.deleteDatabase("kral_local.db")
            app.deleteDatabase("kral_local.db.plaintext-legacy")
            app.deleteDatabase("kral_local.db.cipher-staging")
        }
    }

    private fun allText(view: View): String = when (view) {
        is TextView -> view.text.toString()
        is ViewGroup -> (0 until view.childCount).joinToString(" ") { allText(view.getChildAt(it)) }
        else -> ""
    }
}
