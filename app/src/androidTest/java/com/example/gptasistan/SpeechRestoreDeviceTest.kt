package com.example.gptasistan

import android.app.Activity
import android.os.Bundle
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith

/** Simulates the credential result; it does not test the Android credential UI. */
@RunWith(AndroidJUnit4::class)
class SpeechRestoreDeviceTest {
    @Suppress("DEPRECATION")
    @Test fun restoredActivityAppliesSpeechOnlyAfterSuccessfulCredentialResult() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        InstrumentationSafety.requireDisposableEmulator(context)
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            scenario.onActivity { activity ->
                val state = Bundle().apply { putString("draft", "Önce") }
                val stateField = MainActivity::class.java.getDeclaredField("initialState")
                stateField.isAccessible = true
                stateField.set(activity, state)
                val method = MainActivity::class.java.getDeclaredMethod("applySpeechDraft", List::class.java)
                method.isAccessible = true
                val action: () -> Unit = { method.invoke(activity, listOf("sonra")) }
                val pending = MainActivity::class.java.getDeclaredField("pendingUnlock")
                pending.isAccessible = true
                pending.set(activity, action)

                assertNull(findInput(activity.window.decorView))
                activity.onActivityResult(4701, Activity.RESULT_CANCELED, null)
                assertNull(findInput(activity.window.decorView))

                pending.set(activity, action)
                activity.onActivityResult(4701, Activity.RESULT_OK, null)
                assertEquals("Önce sonra", findInput(activity.window.decorView)?.text.toString())
            }
        }
    }

    private fun findInput(view: View): EditText? {
        if (view is EditText) return view
        if (view is ViewGroup) {
            for (index in 0 until view.childCount) {
                findInput(view.getChildAt(index))?.let { return it }
            }
        }
        return null
    }
}
