package com.example.gptasistan

import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [30])
class KralControlSectionsTest {
    @Test fun opensChatAndChangesOnlyVisibleSection() {
        val context = RuntimeEnvironment.getApplication()
        val root = LinearLayout(context)
        val tabs = KralControlSections(context)
        tabs.attach(root)

        val container = root.getChildAt(1) as FrameLayout
        assertEquals(2, root.childCount)
        assertEquals(View.VISIBLE, container.getChildAt(0).visibility)
        assertEquals(View.GONE, container.getChildAt(1).visibility)
        assertEquals(View.GONE, container.getChildAt(2).visibility)

        tabs.navigation.getChildAt(1).performClick()
        assertEquals(View.GONE, container.getChildAt(0).visibility)
        assertEquals(View.VISIBLE, container.getChildAt(1).visibility)
        assertEquals(View.GONE, container.getChildAt(2).visibility)

        tabs.navigation.getChildAt(2).performClick()
        assertEquals(View.GONE, container.getChildAt(1).visibility)
        assertEquals(View.VISIBLE, container.getChildAt(2).visibility)
    }

    @Test fun switchingTabsNeverExecutesTaskOrErasesDraft() {
        val context = RuntimeEnvironment.getApplication()
        val root = LinearLayout(context)
        val tabs = KralControlSections(context)
        val draft = EditText(context).apply { setText("Korunan taslak") }
        tabs.chat.addView(draft)
        var taskCalls = 0
        tabs.tasks.addView(Button(context).apply {
            setOnClickListener { taskCalls++ }
        })
        tabs.attach(root)

        tabs.show(KralControlSections.Page.TASKS)
        tabs.show(KralControlSections.Page.SYSTEM)
        tabs.show(KralControlSections.Page.CHAT)
        assertEquals(0, taskCalls)
        assertEquals("Korunan taslak", draft.text.toString())
    }

    @Test fun navigationIsLabeledAndHas48dpMinimumTapHeight() {
        val context = RuntimeEnvironment.getApplication()
        val tabs = KralControlSections(context)
        val labels = listOf("Sohbet", "Görevler", "Sistem")
        val minimum = (48f * context.resources.displayMetrics.density + 0.5f).toInt()

        assertEquals(3, tabs.navigation.childCount)
        labels.forEachIndexed { index, label ->
            val button = tabs.navigation.getChildAt(index) as Button
            assertEquals(label, button.text.toString())
            assertEquals(label, button.contentDescription.toString())
            assertTrue(button.minimumHeight >= minimum)
        }
    }
}
