package com.example.gptasistan.billing

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PlayPurchaseSubmissionTest {
    private val expected = "com.example.gptasistan.genesis"

    @Test fun validSubmission() {
        assertTrue(PlayPurchaseSubmission("orba_pro_monthly", "opaque-token_123", expected).validate(expected))
    }

    @Test fun wrongPackageDenied() {
        assertFalse(PlayPurchaseSubmission("orba_pro_monthly", "token", "another.app").validate(expected))
    }

    @Test fun emptyTokenDenied() {
        assertFalse(PlayPurchaseSubmission("orba_pro_monthly", "", expected).validate(expected))
    }

    @Test fun whitespaceTokenDenied() {
        assertFalse(PlayPurchaseSubmission("orba_pro_monthly", "bad token", expected).validate(expected))
    }

    @Test fun emptyProductDenied() {
        assertFalse(PlayPurchaseSubmission("", "token", expected).validate(expected))
    }

    @Test fun suspiciousProductDenied() {
        assertFalse(PlayPurchaseSubmission("../bad", "token", expected).validate(expected))
    }

    @Test fun oversizedTokenDenied() {
        assertFalse(PlayPurchaseSubmission("orba_pro_monthly", "x".repeat(4097), expected).validate(expected))
    }

    @Test fun oversizedProductDenied() {
        assertFalse(PlayPurchaseSubmission("x".repeat(201), "token", expected).validate(expected))
    }

    @Test fun backendLimit101Denied() {
        assertFalse(PlayPurchaseSubmission("x".repeat(101), "token", expected).validate(expected))
    }

    @Test fun exactly100AsciiAccepted() {
        assertTrue(PlayPurchaseSubmission("x".repeat(100), "token", expected).validate(expected))
    }

    @Test fun unicodeProductLetterDenied() {
        assertFalse(PlayPurchaseSubmission("orba_ü", "token", expected).validate(expected))
    }

    @Test fun unicodeProductDigitDenied() {
        assertFalse(PlayPurchaseSubmission("plan_٢", "token", expected).validate(expected))
    }

    @Test fun hyphenInProductDenied() {
        assertFalse(PlayPurchaseSubmission("orba-plan", "token", expected).validate(expected))
    }
}
