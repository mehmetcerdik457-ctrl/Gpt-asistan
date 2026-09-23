package com.example.gptasistan

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.ComponentName
import android.content.Context
import android.graphics.Path
import android.provider.Settings
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import org.json.JSONArray
import org.json.JSONObject
import java.util.ArrayDeque

class PhoneAgentAccessibilityService : AccessibilityService() {
    companion object {
        @Volatile var instance: PhoneAgentAccessibilityService? = null
            private set
        private const val PREFS = "phone_agent_events"
        private const val KEY_EVENTS = "events"
        private const val MAX_EVENTS = 50

        fun isEnabled(context: Context): Boolean {
            val expectedPackage = context.packageName
            val expectedClass = PhoneAgentAccessibilityService::class.java.name
            val enabled = Settings.Secure.getString(
                context.contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
            ) ?: return false
            return enabled.split(':').mapNotNull(ComponentName::unflattenFromString).any {
                it.packageName == expectedPackage && it.className == expectedClass
            }
        }

        fun readEvents(context: Context): JSONArray {
            val raw = context.getSharedPreferences(PREFS, MODE_PRIVATE)
                .getString(KEY_EVENTS, "[]") ?: "[]"
            return runCatching { JSONArray(raw) }.getOrElse { JSONArray() }
        }

        fun clearEvents(context: Context) {
            context.getSharedPreferences(PREFS, MODE_PRIVATE)
                .edit().putString(KEY_EVENTS, "[]").apply()
        }

        private fun appendEvent(context: Context, event: JSONObject) {
            val existing = readEvents(context)
            val trimmed = JSONArray()
            val start = maxOf(0, existing.length() - (MAX_EVENTS - 1))
            for (i in start until existing.length()) trimmed.put(existing.get(i))
            trimmed.put(event)
            context.getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                .putString(KEY_EVENTS, trimmed.toString()).apply()
        }
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        record("SERVICE", "READY", "Accessibility service connected")
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        record("SERVICE", "STOPPED", "Accessibility service destroyed")
        super.onDestroy()
    }

    override fun onInterrupt() {
        record("SERVICE", "INTERRUPTED", "Accessibility service interrupted")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event?.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            val pkg = event.packageName?.toString().orEmpty()
            val cls = event.className?.toString().orEmpty()
            record("WINDOW", "OBSERVED", pkg + "/" + cls)
        }
    }

    fun execute(action: PhoneActionType, text: String? = null, x: Float? = null, y: Float? = null): Boolean {
        if (!PhoneActionPolicy.isAllowed(action)) {
            record(action.name, "DENY", "Policy denied")
            return false
        }
        return when (action) {
            PhoneActionType.BACK -> global(action, GLOBAL_ACTION_BACK)
            PhoneActionType.HOME -> global(action, GLOBAL_ACTION_HOME)
            PhoneActionType.RECENTS -> global(action, GLOBAL_ACTION_RECENTS)
            PhoneActionType.TAP -> if (x == null || y == null) {
                record(action.name, "FAIL", "Missing coordinates"); false
            } else tap(x, y)
            PhoneActionType.CLICK_TEXT -> if (text.isNullOrBlank()) {
                record(action.name, "FAIL", "Missing visible text"); false
            } else clickVisibleText(text)
            PhoneActionType.SCROLL_FORWARD -> scroll(action, AccessibilityNodeInfo.ACTION_SCROLL_FORWARD)
            PhoneActionType.SCROLL_BACKWARD -> scroll(action, AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD)
        }
    }

    private fun global(action: PhoneActionType, globalAction: Int): Boolean {
        val ok = performGlobalAction(globalAction)
        record(action.name, if (ok) "PASS" else "FAIL", "performGlobalAction=" + globalAction)
        return ok
    }

    private fun tap(x: Float, y: Float): Boolean {
        val path = Path().apply { moveTo(x, y) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 80)).build()
        val accepted = dispatchGesture(gesture, object : GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) {
                record("TAP", "PASS", "x=" + x + " y=" + y)
            }
            override fun onCancelled(gestureDescription: GestureDescription?) {
                record("TAP", "FAIL", "gesture cancelled x=" + x + " y=" + y)
            }
        }, null)
        if (!accepted) record("TAP", "FAIL", "dispatchGesture rejected")
        else record("TAP", "ACCEPTED", "x=" + x + " y=" + y)
        return accepted
    }

    private fun clickVisibleText(text: String): Boolean {
        val root = rootInActiveWindow ?: run {
            record("CLICK_TEXT", "FAIL", "No active window"); return false
        }
        val matches = root.findAccessibilityNodeInfosByText(text)
        val target = matches.asSequence()
            .filter { it.isVisibleToUser && it.isEnabled }
            .mapNotNull { clickableAncestor(it) }.firstOrNull()
        val ok = target?.performAction(AccessibilityNodeInfo.ACTION_CLICK) == true
        record("CLICK_TEXT", if (ok) "PASS" else "FAIL", "text=" + text + " matches=" + matches.size)
        return ok
    }

    private fun clickableAncestor(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        var current: AccessibilityNodeInfo? = node
        repeat(8) {
            if (current?.isClickable == true) return current
            current = current?.parent
        }
        return null
    }

    private fun scroll(action: PhoneActionType, androidAction: Int): Boolean {
        val root = rootInActiveWindow ?: run {
            record(action.name, "FAIL", "No active window"); return false
        }
        val target = findFirstScrollable(root)
        val ok = target?.performAction(androidAction) == true
        record(action.name, if (ok) "PASS" else "FAIL", "scrollable=" + (target != null))
        return ok
    }

    private fun findFirstScrollable(root: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        val queue = ArrayDeque<AccessibilityNodeInfo>()
        queue.add(root)
        var visited = 0
        while (queue.isNotEmpty() && visited < 400) {
            val node = queue.removeFirst()
            visited++
            if (node.isVisibleToUser && node.isScrollable) return node
            for (i in 0 until node.childCount) node.getChild(i)?.let(queue::addLast)
        }
        return null
    }

    private fun record(action: String, status: String, detail: String) {
        appendEvent(applicationContext, JSONObject()
            .put("timestamp_ms", System.currentTimeMillis())
            .put("action", action).put("status", status).put("detail", detail))
    }
}
