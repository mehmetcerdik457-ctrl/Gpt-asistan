package com.example.gptasistan

/** Converts explicit speech-recognizer output to a draft. Never sends the result. */
internal object SpeechDraft {
    private const val MAX_DRAFT_CHARS = 16000

    fun merge(existing: String, hypotheses: List<String>?): String? {
        val spoken = hypotheses.orEmpty().asSequence()
            .map { it.replace(Regex("\\s+"), " ").trim() }
            .firstOrNull { it.isNotEmpty() } ?: return null
        val draft = if (existing.isBlank()) spoken else existing.trimEnd() + " " + spoken
        return draft.take(MAX_DRAFT_CHARS)
    }
}
