package com.example.gptasistan

import org.junit.Assert.*
import org.junit.Test

class KralReadOutputTest {
    @Test fun shortResultsAndEmptyMessagesRemainUnchanged() {
        assertEquals("(kayıt yok)", KralAndroidCore.localReadReply(emptyList(), "(kayıt yok)"))
        assertEquals("İstanbul 🙂\nAnkara", KralAndroidCore.localReadReply(
            listOf("İstanbul 🙂", "Ankara"), "empty"))
    }

    @Test fun anExactBudgetDoesNotNeedATruncationNotice() {
        val original = "x".repeat(KralAndroidCore.MAX_LOCAL_READ_REPLY_CHARS)
        assertEquals(original, KralAndroidCore.localReadReply(listOf(original), "empty"))
    }

    @Test fun truncationNoticeAndAllSeparatorsAreIncludedInTheBudget() {
        val reply = KralAndroidCore.localReadReply(List(3) { "not-$it " + "x".repeat(11_000) }, "empty")
        assertTrue(reply.startsWith("not-0 "))
        assertTrue(reply.contains("not-1 "))
        assertTrue(reply.endsWith(KralAndroidCore.READ_TRUNCATION_NOTICE))
        assertTrue(reply.length <= KralAndroidCore.MAX_LOCAL_READ_REPLY_CHARS)
        assertTrue(reply.length < KralAndroidCore.MAX_LEDGER_RESULT_CHARS)
    }

    @Test fun aCharacterLimitNeverSplitsASupplementaryCodePoint() {
        val budget = KralAndroidCore.MAX_LOCAL_READ_REPLY_CHARS -
            KralAndroidCore.READ_TRUNCATION_NOTICE.length
        // Put a surrogate pair exactly across the available display boundary.
        val original = "x".repeat(budget - 1) + "🙂" + "y".repeat(100)
        val reply = KralAndroidCore.localReadReply(listOf(original), "empty")
        assertEquals("x".repeat(budget - 1) + KralAndroidCore.READ_TRUNCATION_NOTICE, reply)
        assertFalse(reply.any { Character.isSurrogate(it) })
    }

    @Test fun aRowLimitIsExplicitEvenWhenTheDisplayedRowsAreShort() {
        assertEquals("Son kayıt" + KralAndroidCore.READ_TRUNCATION_NOTICE,
            KralAndroidCore.localReadReply(listOf("Son kayıt"), "empty", moreRows = true))
    }

    @Test fun aRowLimitAlsoReservesSpaceForItsNoticeAtTheLengthBoundary() {
        val original = "x".repeat(KralAndroidCore.MAX_LOCAL_READ_REPLY_CHARS)
        val reply = KralAndroidCore.localReadReply(listOf(original), "empty", moreRows = true)
        assertEquals(KralAndroidCore.MAX_LOCAL_READ_REPLY_CHARS, reply.length)
        assertTrue(reply.endsWith(KralAndroidCore.READ_TRUNCATION_NOTICE))
    }
}
