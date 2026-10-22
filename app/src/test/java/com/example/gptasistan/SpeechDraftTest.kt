package com.example.gptasistan

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SpeechDraftTest {
    @Test fun recognizesTurkishAndNormalizesWhitespace() {
        assertEquals("Merhaba KRAL", SpeechDraft.merge("", listOf("  Merhaba   KRAL\n")))
    }

    @Test fun appendsToUnsentDraft() {
        assertEquals("Önce sonra", SpeechDraft.merge("Önce", listOf("sonra")))
    }

    @Test fun emptyOrCancelledResultKeepsDraftUntouched() {
        assertNull(SpeechDraft.merge("koru", null))
        assertNull(SpeechDraft.merge("koru", listOf("", "  ")))
    }

    @Test fun choosesFirstNonBlankHypothesis() {
        assertEquals("ses", SpeechDraft.merge("", listOf("", "  ses  ", "başka")))
    }

    @Test fun neverExceedsInputFilterLength() {
        assertEquals(16000, SpeechDraft.merge("x".repeat(15999), listOf("abc"))!!.length)
    }
}
