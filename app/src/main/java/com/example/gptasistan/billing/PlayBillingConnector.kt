package com.example.gptasistan.billing

import android.content.Context
import android.app.Activity
import com.android.billingclient.api.BillingClient
import com.android.billingclient.api.BillingClientStateListener
import com.android.billingclient.api.BillingResult
import com.android.billingclient.api.PendingPurchasesParams
import com.android.billingclient.api.Purchase
import com.android.billingclient.api.QueryPurchasesParams
import com.android.billingclient.api.PurchasesUpdatedListener
import com.android.billingclient.api.QueryProductDetailsParams
import com.android.billingclient.api.BillingFlowParams

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

    /** Read eligible Play subscription offers; never accept pricing from a client. */
    fun querySubscriptionOffers(
        productId: String,
        onResult: (Int, List<PlaySubscriptionOffer>) -> Unit
    ) {
        if (!PlaySubscriptionCheckout.isValidProductId(productId)) {
            onResult(BillingClient.BillingResponseCode.DEVELOPER_ERROR, emptyList())
            return
        }
        if (!client.isReady) {
            onResult(BillingClient.BillingResponseCode.SERVICE_DISCONNECTED, emptyList())
            return
        }
        val supported = client.isFeatureSupported(BillingClient.FeatureType.SUBSCRIPTIONS)
        if (supported.responseCode != BillingClient.BillingResponseCode.OK) {
            onResult(supported.responseCode, emptyList())
            return
        }
        val params = QueryProductDetailsParams.newBuilder()
            .setProductList(listOf(QueryProductDetailsParams.Product.newBuilder()
                .setProductId(productId)
                .setProductType(BillingClient.ProductType.SUBS)
                .build()))
            .build()
        client.queryProductDetailsAsync(params) { result, details ->
            if (result.responseCode != BillingClient.BillingResponseCode.OK) {
                onResult(result.responseCode, emptyList())
                return@queryProductDetailsAsync
            }
            val offers = details.productDetailsList
                .filter { it.productId == productId }
                .flatMap { detail ->
                    detail.subscriptionOfferDetails.orEmpty().map { offer ->
                        PlaySubscriptionOffer(offer.basePlanId, offer.offerId, offer.offerToken)
                    }
                }
            onResult(
                if (offers.isNotEmpty()) BillingClient.BillingResponseCode.OK
                else BillingClient.BillingResponseCode.ITEM_UNAVAILABLE,
                offers
            )
        }
    }

    /**
     * Starts Google Play's purchase UI ONLY when explicitly called by the app
     * after user selects an eligible offer and the authenticated backend
     * provides its HMAC-derived obfuscated account identifier.
     *
     * It re-queries a FRESH ProductDetails object (no stale offer caching).
     * BillingFlowParams success is NOT proof of purchase or entitlement.
     */
    fun launchSelectedSubscription(
        activity: Activity,
        checkout: PlaySubscriptionCheckout,
        onResult: (Int) -> Unit
    ) {
        if (!checkout.validate()) {
            onResult(BillingClient.BillingResponseCode.DEVELOPER_ERROR)
            return
        }
        if (!client.isReady) {
            onResult(BillingClient.BillingResponseCode.SERVICE_DISCONNECTED)
            return
        }
        val supported = client.isFeatureSupported(BillingClient.FeatureType.SUBSCRIPTIONS)
        if (supported.responseCode != BillingClient.BillingResponseCode.OK) {
            onResult(supported.responseCode)
            return
        }
        val params = QueryProductDetailsParams.newBuilder()
            .setProductList(listOf(QueryProductDetailsParams.Product.newBuilder()
                .setProductId(checkout.productId)
                .setProductType(BillingClient.ProductType.SUBS)
                .build()))
            .build()
        client.queryProductDetailsAsync(params) { result, details ->
            if (result.responseCode != BillingClient.BillingResponseCode.OK) {
                onResult(result.responseCode)
                return@queryProductDetailsAsync
            }
            val product = details.productDetailsList.singleOrNull {
                it.productId == checkout.productId
            }
            val offer = product?.subscriptionOfferDetails
                ?.singleOrNull { it.offerToken == checkout.offerToken }
            if (product == null || offer == null) {
                onResult(BillingClient.BillingResponseCode.ITEM_UNAVAILABLE)
                return@queryProductDetailsAsync
            }
            activity.runOnUiThread {
                val productParams = BillingFlowParams.ProductDetailsParams.newBuilder()
                    .setProductDetails(product)
                    .setOfferToken(offer.offerToken)
                    .build()
                val flow = BillingFlowParams.newBuilder()
                    .setProductDetailsParamsList(listOf(productParams))
                    .setObfuscatedAccountId(checkout.obfuscatedAccountId)
                    .build()
                val response = client.launchBillingFlow(activity, flow)
                onResult(response.responseCode)
            }
        }
    }

    fun close() = client.endConnection()
}
