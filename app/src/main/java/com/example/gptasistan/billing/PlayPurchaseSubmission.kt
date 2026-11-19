package com.example.gptasistan.billing

/**
 * Pure input-validation boundary for passing a Google Play purchase to an
 * authenticated backend. Does not grant entitlement or call Google Play.
 *
 * The backend must derive account identity from its authenticated session,
 * independently verify the token using the Google Play Developer API, and
 * decide entitlement. Never trust a client-provided verification flag.
 */
internal data class PlayPurchaseSubmission(
    val productId: String,
    val purchaseToken: String,
    val packageName: String
) {
    fun validate(expectedPackageName: String): Boolean =
        expectedPackageName.isNotBlank() &&
        packageName == expectedPackageName &&
        PlaySubscriptionCheckout.isValidProductId(productId) &&
        purchaseToken.length in 1..4096 &&
        purchaseToken.all { it in 'A'..'Z' || it in 'a'..'z' || it in '0'..'9' ||
                            it == '.' || it == '_' || it == '~' || it == '%' || it == '-' }

    override fun toString() = "PlayPurchaseSubmission(productId=$productId, purchaseToken=<redacted>, packageName=$packageName)"
}

/**
 * Only a trusted authenticated transport may implement this interface.
 * Implementations must not log tokens, persist them in plaintext, or treat
 * HTTP success as a grant of entitlement.
 */
internal interface AuthenticatedPlayPurchaseTransport {
    /** Both operations are blocking and must run on a worker thread. */
    fun account(): PlayAccountConfiguration
    fun submit(submission: PlayPurchaseSubmission): Boolean
}

internal data class PlayAccountConfiguration(val obfuscatedAccountId: String, val products: List<String>) {
    fun validate() = obfuscatedAccountId.matches(Regex("[a-f0-9]{64}")) &&
        products.size in 1..32 && products.distinct().size == products.size &&
        products.all { PlaySubscriptionCheckout.isValidProductId(it) }
}
