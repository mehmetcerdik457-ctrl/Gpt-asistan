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
        offerToken.length in 1..2048 &&
        offerToken.all { it.code in 33..126 } &&
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
    val productId: String,
    val displayName: String,
    val basePlanId: String,
    val offerId: String?,
    val offerToken: String,
    val pricingPhases: List<PlayPricingPhase>
) {
    fun validate() = PlaySubscriptionCheckout.isValidProductId(productId) &&
        displayName.isNotBlank() && displayName.length <= 300 &&
        displayName.none { it.isISOControl() } &&
        offerToken.length in 1..2048 && offerToken.all { it.code in 33..126 } &&
        pricingPhases.size in 1..32 && pricingPhases.all { it.validate() }

    fun priceDescription(): String = pricingPhases.joinToString(" → ") { it.description() }
}

internal data class PlayPricingPhase(
    val formattedPrice: String,
    val billingPeriod: String,
    val billingCycleCount: Int,
    val recurrenceMode: Int
) {
    fun validate() = formattedPrice.isNotBlank() && formattedPrice.length <= 100 &&
        formattedPrice.none { it.isISOControl() } &&
        billingPeriod.matches(Regex("P[1-9][0-9]{0,3}[DWMY]")) &&
        billingCycleCount in 0..1000 && recurrenceMode in 1..3 &&
        (recurrenceMode != 2 || billingCycleCount > 0)

    fun description(): String {
        val amount = billingPeriod.drop(1).dropLast(1)
        val unit = when (billingPeriod.lastOrNull()) {
            'D' -> "gün"; 'W' -> "hafta"; 'M' -> "ay"; 'Y' -> "yıl"; else -> "dönem"
        }
        val renewal = when (recurrenceMode) {
            1 -> "otomatik yenilenir"
            2 -> "$billingCycleCount dönem"
            else -> "tek dönem"
        }
        return "$formattedPrice / $amount $unit ($renewal)"
    }
}
