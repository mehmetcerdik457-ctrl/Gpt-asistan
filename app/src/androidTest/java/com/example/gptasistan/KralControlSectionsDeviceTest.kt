package com.example.gptasistan

import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Real Android view-level assertions on the CI emulator (API 30 and 36).
 * These tests do not bypass the device credential prompt and do not touch
 * the owner's encrypted database, provider credentials, or external apps.
 */
@RunWith(AndroidJUnit4::class)
class KralControlSectionsDeviceTest {
    @Test fun sectionNavigationOnlyChangesVisibilityAndPreservesDraft() {
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            val context = InstrumentationRegistry.getInstrumentation().targetContext
            val root = LinearLayout(context)
            val sections = KralControlSections(context)
            val draft = EditText(context).apply { setText("Gizli taslak korunur") }
            sections.chat.addView(draft)
            var externalActions = 0
            sections.tasks.addView(Button(context).apply {
                setOnClickListener { externalActions++ }
            })
            sections.attach(root)
            val pages = root.getChildAt(1) as FrameLayout
            assertEquals(View.VISIBLE, pages.getChildAt(0).visibility)
            assertEquals(View.GONE, pages.getChildAt(1).visibility)
            assertEquals(View.GONE, pages.getChildAt(2).visibility)

            sections.navigation.getChildAt(1).performClick()
            assertEquals(View.VISIBLE, pages.getChildAt(1).visibility)
            sections.navigation.getChildAt(2).performClick()
            assertEquals(View.VISIBLE, pages.getChildAt(2).visibility)
            sections.navigation.getChildAt(0).performClick()
            assertEquals(View.VISIBLE, pages.getChildAt(0).visibility)

            assertEquals(0, externalActions)
            assertEquals("Gizli taslak korunur", draft.text.toString())
        }
    }

    @Test fun navigationHasLabelsAndMinimum48DpTapHeight() {
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            val context = InstrumentationRegistry.getInstrumentation().targetContext
            val sections = KralControlSections(context)
            val labels = listOf("Sohbet", "Görevler", "Sistem")
            val minHeightPx = (48f * context.resources.displayMetrics.density + 0.5f).toInt()
            assertEquals(labels.size, sections.navigation.childCount)
            labels.forEachIndexed { i, label ->
                val button = sections.navigation.getChildAt(i) as Button
                assertEquals(label, button.text.toString())
                assertEquals(label, button.contentDescription.toString())
                assertTrue(button.minimumHeight >= minHeightPx)
            }
        }
    }

    @Test fun ownerLockHidesAllNewPagesUntilCredentialVerification() {
        val scenario = ActivityScenario.launch(MainActivity::class.java)
        try {
            scenario.onActivity { activity ->
                val visibleLabels = mutableListOf<String>()
                fun visit(view: View) {
                    if (view.visibility != View.VISIBLE) return
                    if (view is TextView) visibleLabels.add(view.text.toString())
                    if (view is ViewGroup) {
                        for (i in 0 until view.childCount) visit(view.getChildAt(i))
                    }
                }
                visit(activity.window.decorView)
                assertTrue(visibleLabels.any { it.contains("Kilidi aç") })
                assertFalse(visibleLabels.any { it == "Sohbet" })
                assertFalse(visibleLabels.any { it == "Görevler" })
                assertFalse(visibleLabels.any { it == "Sistem" })
            }
        } finally {
            scenario.close()
        }
    }
}
