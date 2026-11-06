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
    /** Plain clipboard return only; the origin cannot be authenticated. */
    fun importableReply(text: CharSequence?): String? {
        val raw = text?.toString() ?: return null
        if (raw.length > MAX_CLIPBOARD_CHARS) return null
        val trimmed = raw.trim()
        if (trimmed.isEmpty()) return null
        if (trimmed.any { c ->
                c == '\u0000' || (c.code < 32 && c != '\n' && c != '\r' && c != '\t')
            }
        ) return null
        return trimmed
    }
}
