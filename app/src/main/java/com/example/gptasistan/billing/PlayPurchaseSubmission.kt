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
        productId.isNotBlank() &&
        productId.length <= 200 &&
        productId.all { it.isLetterOrDigit() || it == '_' || it == '.' } &&
        purchaseToken.isNotBlank() &&
        purchaseToken.length <= 4096 &&
        purchaseToken.none { it.isWhitespace() }
}

/**
 * Only a trusted authenticated transport may implement this interface.
 * Implementations must not log tokens, persist them in plaintext, or treat
 * HTTP success as a grant of entitlement.
 */
internal fun interface AuthenticatedPlayPurchaseTransport {
    suspend fun submit(submission: PlayPurchaseSubmission): Boolean
}
