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

    @Test fun productMatchesExactAsciiServerContract() {
        for (product in listOf("caf\u00e9", "\u043f\u0440\u043e\u0434\u0443\u043a\u0442", "a".repeat(101)))
            assertFalse(product, PlayPurchaseSubmission(product, "token", expected).validate(expected))
        assertTrue(PlayPurchaseSubmission("a".repeat(100), "token", expected).validate(expected))
    }

    @Test fun controlUnicodeAndUrlDelimitersInTokenDenied() {
        for (token in listOf("token\u0000", "token\u007f", "caf\u00e9", "token/a", "token+a", "token?a", "token=a"))
            assertFalse(PlayPurchaseSubmission("orba_pro_monthly", token, expected).validate(expected))
        assertTrue(PlayPurchaseSubmission("orba_pro_monthly", "abcABC123._~%-", expected).validate(expected))
    }

    @Test fun diagnosticStringNeverContainsPurchaseToken() {
        assertFalse(PlayPurchaseSubmission("orba_pro_monthly", "secret-token-value", expected)
            .toString().contains("secret-token-value"))
    }
}
