package com.mehmetcerdik.ownerai.billing

import android.content.Context
import com.android.billingclient.api.BillingClient
import com.android.billingclient.api.BillingClientStateListener
import com.android.billingclient.api.PendingPurchasesParams
import com.android.billingclient.api.Purchase
import com.android.billingclient.api.PurchasesUpdatedListener
import com.android.billingclient.api.QueryPurchasesParams

/**
 * Thin Play Billing boundary. This client reports purchase tokens only to the app's
 * trusted backend verifier; a client-side PURCHASED state is never treated as entitlement.
 */
class PlayBillingGateway(
    context: Context,
    private val onPurchasesUpdated: (responseCode: Int, purchases: List<Purchase>?) -> Unit
) {
    private val listener = PurchasesUpdatedListener { result, purchases ->
        onPurchasesUpdated(result.responseCode, purchases)
    }

    private val client: BillingClient = BillingClient.newBuilder(context.applicationContext)
        .setListener(listener)
        .enablePendingPurchases(
            PendingPurchasesParams.newBuilder()
                .enableOneTimeProducts()
                .build()
        )
        .build()

    fun connect(onConnected: (Boolean, String?) -> Unit) {
        if (client.isReady) {
            onConnected(true, null)
            return
        }
        client.startConnection(object : BillingClientStateListener {
            override fun onBillingSetupFinished(result: com.android.billingclient.api.BillingResult) {
                onConnected(
                    result.responseCode == BillingClient.BillingResponseCode.OK,
                    result.debugMessage
                )
            }

            override fun onBillingServiceDisconnected() {
                onConnected(false, "PLAY_BILLING_SERVICE_DISCONNECTED")
            }
        })
    }

    fun queryActiveSubscriptions(onResult: (Int, List<Purchase>) -> Unit) {
        if (!client.isReady) {
            onResult(BillingClient.BillingResponseCode.SERVICE_DISCONNECTED, emptyList())
            return
        }
        val params = QueryPurchasesParams.newBuilder()
            .setProductType(BillingClient.ProductType.SUBS)
            .build()
        client.queryPurchasesAsync(params) { result, purchases ->
            onResult(result.responseCode, purchases)
        }
    }

    fun disconnect() {
        if (client.isReady) client.endConnection()
    }
}

/** Implement on the trusted server. Never validate/activate a subscription from the APK alone. */
fun interface PurchaseTokenValidationPort {
    suspend fun verify(
        packageName: String,
        productId: String,
        purchaseToken: String
    ): ServerPurchaseValidation
}

data class ServerPurchaseValidation(
    val valid: Boolean,
    val entitlementId: String?,
    val expiresAtEpochMillis: Long?,
    val reasonCode: String
)
