package com.example.gptasistan.billing

import java.security.MessageDigest
import java.util.concurrent.Executor

/** Small testable state machine. Billing results never substitute for server verification. */
internal interface PlayBillingPort {
    fun connect(onReady: (Int) -> Unit)
    fun offers(product: String, onResult: (Int, List<PlaySubscriptionOffer>) -> Unit)
    fun restore(onComplete: (Int, Int) -> Unit)
    fun launch(checkout: PlaySubscriptionCheckout, onResult: (Int) -> Unit)
    fun close()
}

internal enum class PlayBillingStatus {
    LOADING, READY, NO_OFFERS, RESTORING, NO_PURCHASES, VERIFYING,
    VERIFIED, DENIED, PENDING, CANCELED, OPENING_PLAY, PLAY_OPENED, UNAVAILABLE
}

internal data class PlayBillingState(
    val status: PlayBillingStatus,
    val offers: List<PlaySubscriptionOffer>,
    val busy: Boolean
)

internal class PlayBillingFlow(
    private val packageName: String,
    private val transport: AuthenticatedPlayPurchaseTransport,
    private val billing: PlayBillingPort,
    private val worker: Executor,
    private val dispatch: (() -> Unit) -> Unit,
    private val authorized: () -> Boolean,
    private val render: (PlayBillingState) -> Unit
) {
    @Volatile private var closed = false
    private var started = false
    private var connected = false
    private var loading = false
    private var restoring = false
    private var checkoutPending = false
    private var account: PlayAccountConfiguration? = null
    private var available = emptyList<PlaySubscriptionOffer>()
    private val verifying = mutableSetOf<String>()
    // Ephemeral results of the current reconciliation, never an authorization cache.
    private val verificationResults = mutableMapOf<String, Boolean?>()
    private var status = PlayBillingStatus.LOADING
    private var catalogGeneration = 0

    private fun active() = !closed && authorized()
    private fun busy() = loading || restoring || checkoutPending || verifying.isNotEmpty()

    private fun show(next: PlayBillingStatus = status) {
        if (!active()) return
        status = next
        render(PlayBillingState(status, available.toList(), busy()))
    }

    private fun background(action: () -> Unit) {
        try { worker.execute { if (active()) action() } }
        catch (_: Exception) { unavailable() }
    }

    private fun deliver(action: () -> Unit) = dispatch { if (active()) action() }

    private fun unavailable() {
        connected = false
        loading = false
        restoring = false
        checkoutPending = false
        show(PlayBillingStatus.UNAVAILABLE)
    }

    fun start() {
        if (!active() || started) return
        started = true
        loadAccount()
    }

    /** Reconcile owned purchases after app return or a previous transient error. */
    fun refresh() {
        if (!active() || !started || busy()) return
        loadAccount()
    }

    private fun loadAccount() {
        loading = true
        verificationResults.clear()
        available = emptyList()
        show(PlayBillingStatus.LOADING)
        background {
            val fresh = try { transport.account().also { require(it.validate()) } }
                catch (_: Exception) { deliver { unavailable() }; return@background }
            deliver {
                account = fresh.copy(products = fresh.products.toList())
                if (connected) loadOffersAndRestore()
                else try {
                    billing.connect { code -> deliver {
                        if (code == 0) { connected = true; loadOffersAndRestore() }
                        else unavailable()
                    } }
                } catch (_: Exception) { unavailable() }
            }
        }
    }

    private fun loadOffersAndRestore() {
        val products = account?.products ?: return unavailable()
        val generation = ++catalogGeneration
        var remaining = products.size
        val found = mutableListOf<PlaySubscriptionOffer>()
        val completed = mutableSetOf<String>()
        fun completeProduct(product: String, code: Int, offers: List<PlaySubscriptionOffer>) {
            if (generation != catalogGeneration || !completed.add(product)) return
            if (code == 0 && offers.size <= 64)
                found += offers.filter { it.productId == product && it.validate() }
            remaining--
            if (remaining == 0) {
                available = found.groupBy { it.productId to it.offerToken }.values
                    .filter { it.size == 1 }.map { it.single() }.take(128)
                loading = false
                if (status in setOf(PlayBillingStatus.LOADING, PlayBillingStatus.RESTORING))
                    show(if (available.isEmpty()) PlayBillingStatus.NO_OFFERS else PlayBillingStatus.READY)
                else show()
            }
        }
        for (product in products) {
            try {
                billing.offers(product) { code, offers -> deliver {
                    completeProduct(product, code, offers)
                } }
            } catch (_: Exception) {
                completeProduct(product, -1, emptyList())
            }
        }
        restoring = true
        show(PlayBillingStatus.RESTORING)
        try {
            billing.restore { code, count -> deliver {
                restoring = false
                when {
                    code != 0 -> { connected = false; show(PlayBillingStatus.UNAVAILABLE) }
                    count == 0 -> show(PlayBillingStatus.NO_PURCHASES)
                    verifying.isNotEmpty() -> show(PlayBillingStatus.VERIFYING)
                    else -> show()
                }
            } }
        } catch (_: Exception) { restoring = false; show(PlayBillingStatus.UNAVAILABLE) }
    }

    /** Called only for a user's selected real offer. Fetch account binding again before launch. */
    fun buy(offer: PlaySubscriptionOffer) {
        if (!active() || busy() || !connected || offer !in available || !offer.validate()) return
        checkoutPending = true
        show(PlayBillingStatus.OPENING_PLAY)
        background {
            val fresh = try { transport.account().also { require(it.validate()) } }
                catch (_: Exception) { deliver { unavailable() }; return@background }
            deliver {
                if (offer.productId !in fresh.products || offer !in available) return@deliver unavailable()
                val checkout = PlaySubscriptionCheckout(offer.productId, offer.offerToken, fresh.obfuscatedAccountId)
                if (!checkout.validate()) return@deliver unavailable()
                try { billing.launch(checkout) { code -> deliver {
                    if (code == 0) show(PlayBillingStatus.PLAY_OPENED)
                    else {
                        checkoutPending = false
                        show(if (code == 1) PlayBillingStatus.CANCELED else PlayBillingStatus.UNAVAILABLE)
                    }
                } } } catch (_: Exception) { unavailable() }
            }
        }
    }

    /** Purchase/restore callbacks trigger a new authenticated server check, never a local grant. */
    fun purchased(submission: PlayPurchaseSubmission) {
        if (!active()) return
        checkoutPending = false
        if (!submission.validate(packageName) || submission.productId !in account?.products.orEmpty()) {
            show(PlayBillingStatus.DENIED)
            return
        }
        val digest = MessageDigest.getInstance("SHA-256")
            .digest((submission.productId + "\u0000" + submission.purchaseToken).toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it.toInt() and 255) }
        if (!verifying.add(digest)) return
        verificationResults.remove(digest)
        show(PlayBillingStatus.VERIFYING)
        background {
            val result = try { transport.submit(submission) }
                catch (_: Exception) { deliver {
                    verifying.remove(digest)
                    verificationResults[digest] = null
                    show(verificationStatus())
                }; return@background }
            deliver {
                verifying.remove(digest)
                verificationResults[digest] = result
                show(verificationStatus())
            }
        }
    }

    fun pending() { if (active()) { checkoutPending = false; show(PlayBillingStatus.PENDING) } }
    fun canceled() { if (active()) { checkoutPending = false; show(PlayBillingStatus.CANCELED) } }
    fun failed() { if (active()) unavailable() }

    private fun verificationStatus() = when {
        verifying.isNotEmpty() -> PlayBillingStatus.VERIFYING
        verificationResults.values.any { it == true } -> PlayBillingStatus.VERIFIED
        verificationResults.values.any { it == null } -> PlayBillingStatus.UNAVAILABLE
        else -> PlayBillingStatus.DENIED
    }

    fun close() {
        closed = true
        catalogGeneration++
        available = emptyList()
        account = null
        verifying.clear()
        verificationResults.clear()
        try { billing.close() } catch (_: Exception) { }
    }
}
