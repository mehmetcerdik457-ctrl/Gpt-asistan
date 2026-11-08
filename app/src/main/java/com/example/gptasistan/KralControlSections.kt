package com.example.gptasistan

import android.content.Context
import android.graphics.Typeface
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView

/**
 * UI-only navigation. Switching pages cannot execute model, CİHAT, Owner
 * or OMEGA operations. Existing action handlers remain in MainActivity.
 */
internal class KralControlSections(private val context: Context) {
    internal enum class Page { CHAT, TASKS, SYSTEM }

    val chat = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
    val tasks = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
    val system = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
    val navigation = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL }

    private val content = FrameLayout(context)
    private val labels = mapOf(
        Page.CHAT to R.string.nav_chat,
        Page.TASKS to R.string.nav_tasks,
        Page.SYSTEM to R.string.nav_system
    )
    private val buttons = mutableMapOf<Page, Button>()
    private val taskScroll = ScrollView(context).apply {
        isFillViewport = true
        addView(tasks, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT))
    }
    private val systemScroll = ScrollView(context).apply {
        isFillViewport = true
        addView(system, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT))
    }
    private val pages: Map<Page, View> = mapOf(
        Page.CHAT to chat,
        Page.TASKS to taskScroll,
        Page.SYSTEM to systemScroll
    )

    init {
        val touchHeight = (48f * context.resources.displayMetrics.density + 0.5f).toInt()
        for (page in Page.values()) {
            val button = Button(context).apply {
                text = context.getString(labels.getValue(page))
                contentDescription = text
                isAllCaps = false
                textSize = 13f
                minHeight = touchHeight
                setOnClickListener { show(page) }
            }
            buttons[page] = button
            navigation.addView(button, LinearLayout.LayoutParams(0,
                ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            content.addView(pages.getValue(page), FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        }
        show(Page.CHAT)
    }

    fun attach(root: LinearLayout) {
        root.addView(navigation, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        root.addView(content, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
    }

    fun show(page: Page) {
        pages.forEach { (key, view) ->
            view.visibility = if (key == page) View.VISIBLE else View.GONE
        }
        buttons.forEach { (key, button) ->
            val active = key == page
            button.isSelected = active
            button.setTypeface(null, if (active) Typeface.BOLD else Typeface.NORMAL)
        }
    }
}
