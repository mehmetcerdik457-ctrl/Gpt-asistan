package com.example.gptasistan

/**
 * Explicit owner-mediated inter-app handoff. No proprietary intents, private
 * API keys, background Accessibility or automatic message transmission.
 */
object CihatHandoff {
    const val PACKAGE_NAME = "com.codespaceapps.aichat"
    private const val MAX_CLIPBOARD_CHARS = 2000

    /** Returns only the current typed draft, never memory or saved conversation. */
    fun copyableDraft(currentInput: String): String? {
        val trimmed = currentInput.trim()
        if (trimmed.isEmpty() || trimmed.length > MAX_CLIPBOARD_CHARS) return null
        return trimmed
    }
}
