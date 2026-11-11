package com.example.gptasistan.billing

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PlaySubscriptionCheckoutTest {
    private val id = "a".repeat(64)
    private fun checkout(
        product: String = "orba_pro_monthly",
        offer: String = "offer_token-123+/=",
        account: String = id
    ) = PlaySubscriptionCheckout(product, offer, account)

    @Test fun validBackendObfuscatedIdAndOffer() {
        assertTrue(checkout().validate())
    }
    @Test fun missingProductDenied() {
        assertFalse(checkout(product = "").validate())
    }
    @Test fun slashInProductDenied() {
        assertFalse(checkout(product = "../orba").validate())
    }
    @Test fun oversizedProductDenied() {
        assertFalse(checkout(product = "x".repeat(101)).validate())
    }
    @Test fun missingOfferDenied() {
        assertFalse(checkout(offer = "").validate())
    }
    @Test fun whitespaceOfferDenied() {
        assertFalse(checkout(offer = "bad offer").validate())
    }
    @Test fun oversizedOfferDenied() {
        assertFalse(checkout(offer = "x".repeat(2049)).validate())
    }
    @Test fun rawOwnerStringDenied() {
        assertFalse(checkout(account = "user@example.com").validate())
    }
    @Test fun invalidObfuscatedLengthDenied() {
        assertFalse(checkout(account = "a".repeat(63)).validate())
    }
    @Test fun upperCaseDigestDenied() {
        assertFalse(checkout(account = "F".repeat(64)).validate())
    }
    @Test fun nonHexObfuscatedIdDenied() {
        assertFalse(checkout(account = "g".repeat(64)).validate())
    }
    @Test fun productValidatorAcceptsExactSubscriptionId() {
        assertTrue(PlaySubscriptionCheckout.isValidProductId("orba_pro_monthly"))
    }
}
