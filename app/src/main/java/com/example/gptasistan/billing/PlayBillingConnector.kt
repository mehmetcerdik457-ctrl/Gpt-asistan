package com.example.gptasistan.billing

import android.content.Context
import com.android.billingclient.api.BillingClient
import com.android.billingclient.api.BillingClientStateListener
import com.android.billingclient.api.BillingResult
import com.android.billingclient.api.PendingPurchasesParams
import com.android.billingclient.api.Purchase
import com.android.billingclient.api.QueryPurchasesParams
import com.android.billingclient.api.PurchasesUpdatedListener

/**
 * Isolated BillingClient 9 adapter. It does NOT initiate a checkout or grant
 * entitlements. Caller must provide an authenticated server transport before
 * wiring purchase updates to the verification service.
 *
 * Do not log purchase tokens or use purchase state alone as proof of access.
 */
internal class PlayBillingConnector(
    context: Context,
    private val onPurchased: (PlayPurchaseSubmission) -> Unit,
    private val onFailure: (Int) -> Unit
) : PurchasesUpdatedListener {

    private val packageName = context.packageName

    private val client = BillingClient.newBuilder(context.applicationContext)
        .setListener(this)
        .enablePendingPurchases(
            PendingPurchasesParams.newBuilder().enableOneTimeProducts().build()
        )
        .enableAutoServiceReconnection()
        .build()

    fun connect() {
        client.startConnection(object : BillingClientStateListener {
            override fun onBillingSetupFinished(result: BillingResult) {
                if (result.responseCode == BillingClient.BillingResponseCode.OK) {
                    restoreKnownPurchases()
                } else {
                    onFailure(result.responseCode)
                }
            }

            override fun onBillingServiceDisconnected() {
                // Automatic reconnection is enabled; no entitlement is granted.
            }
        })
    }

    /** Reconcile subscriptions after reconnect or app start, without granting access. */
    fun restoreKnownPurchases() {
        val params = QueryPurchasesParams.newBuilder()
            .setProductType(BillingClient.ProductType.SUBS)
            .build()
        client.queryPurchasesAsync(params) { result, purchases ->
            if (result.responseCode == BillingClient.BillingResponseCode.OK) {
                onPurchasesUpdated(result, purchases.toMutableList())
            } else {
                onFailure(result.responseCode)
            }
        }
    }

    override fun onPurchasesUpdated(result: BillingResult, purchases: MutableList<Purchase>?) {
        if (result.responseCode != BillingClient.BillingResponseCode.OK) {
            if (result.responseCode != BillingClient.BillingResponseCode.USER_CANCELED) {
                onFailure(result.responseCode)
            }
            return
        }
        if (purchases == null) {
            onFailure(BillingClient.BillingResponseCode.ERROR)
            return
        }
        purchases.forEach { purchase ->
            if (purchase.purchaseState != Purchase.PurchaseState.PURCHASED) return@forEach
            purchase.products.forEach { productId ->
                val submission = PlayPurchaseSubmission(
                    productId = productId,
                    purchaseToken = purchase.purchaseToken,
                    packageName = packageName
                )
                if (submission.validate(packageName)) onPurchased(submission)
                else onFailure(BillingClient.BillingResponseCode.ERROR)
            }
        }
    }

    fun close() = client.endConnection()
}
