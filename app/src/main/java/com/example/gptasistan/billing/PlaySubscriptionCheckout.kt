package com.example.gptasistan.billing

/**
 * Minimal validated checkout intent. The opaque account identifier MUST come
 * from the authenticated server. Never embed HMAC key, raw owner ID, or email.
 *
 * This object alone does not start billing or grant any subscription rights.
 */
internal data class PlaySubscriptionCheckout(
    val productId: String,
    val offerToken: String,
    val obfuscatedAccountId: String
) {
    fun validate(): Boolean =
        isValidProductId(productId) &&
        offerToken.isNotBlank() &&
        offerToken.length <= 2048 &&
        offerToken.none { it.isWhitespace() } &&
        obfuscatedAccountId.length == 64 &&
        obfuscatedAccountId.all { it in '0'..'9' || it in 'a'..'f' }

    companion object {
        fun isValidProductId(value: String): Boolean =
            value.length in 1..100 &&
            value.all { it in 'A'..'Z' || it in 'a'..'z' ||
                        it in '0'..'9' || it == '_' || it == '.' }
    }
}

internal data class PlaySubscriptionOffer(
    val basePlanId: String,
    val offerId: String?,
    val offerToken: String
)
