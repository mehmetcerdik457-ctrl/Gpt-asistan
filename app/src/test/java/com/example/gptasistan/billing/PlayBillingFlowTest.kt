package com.example.gptasistan.billing

import org.junit.Assert.*
import org.junit.Test
import java.util.ArrayDeque
import java.util.concurrent.Executor

/** Fakes exercise the actual coordinator; no Billing service, credentials or purchase is used. */
class PlayBillingFlowTest {
    private val product = "orba_pro_monthly"
    private val token = "opaque-token_123"
    private val packageName = "com.example.gptasistan.genesis"
    private val offer = PlaySubscriptionOffer(product, "ORBA Pro", "monthly", null,
        "synthetic-offer+/=", listOf(PlayPricingPhase("₺49,99", "P1M", 0, 1)))

    private class Queue : Executor {
        val tasks = ArrayDeque<Runnable>()
        override fun execute(command: Runnable) { tasks.add(command) }
        fun drain() { while (tasks.isNotEmpty()) tasks.remove().run() }
    }

    private inner class Transport : AuthenticatedPlayPurchaseTransport {
        var account = PlayAccountConfiguration("a".repeat(64), listOf(product))
        var accountCalls = 0
        var submits = 0
        var granted = true
        val results = mutableMapOf<String, Boolean>()
        var fail = false
        override fun account(): PlayAccountConfiguration {
            accountCalls++
            if (fail) throw IllegalStateException("secret-provider-token")
            return account
        }
        override fun submit(submission: PlayPurchaseSubmission): Boolean {
            submits++
            if (fail) throw IllegalStateException(submission.purchaseToken)
            return results[submission.purchaseToken] ?: granted
        }
    }

    private inner class Port : PlayBillingPort {
        var connections = 0
        var restores = 0
        var launches = mutableListOf<PlaySubscriptionCheckout>()
        var offers = listOf(offer)
        var afterRestore: (() -> Unit)? = null
        var restoreCount = 0
        var closed = false
        var delayedOffer: ((Int, List<PlaySubscriptionOffer>) -> Unit)? = null
        var delayOffers = false
        override fun connect(onReady: (Int) -> Unit) { connections++; onReady(0) }
        override fun offers(product: String, onResult: (Int, List<PlaySubscriptionOffer>) -> Unit) {
            if (delayOffers) delayedOffer = onResult else onResult(0, offers)
        }
        override fun restore(onComplete: (Int, Int) -> Unit) {
            restores++
            afterRestore?.invoke()
            onComplete(0, restoreCount)
        }
        override fun launch(checkout: PlaySubscriptionCheckout, onResult: (Int) -> Unit) {
            launches.add(checkout)
            onResult(0)
        }
        override fun close() { closed = true }
    }

    private inner class Fixture {
        val queue = Queue()
        val transport = Transport()
        val port = Port()
        var allowed = true
        val states = mutableListOf<PlayBillingState>()
        val flow = PlayBillingFlow(packageName, transport, port, queue,
            dispatch = { it() }, authorized = { allowed }, render = { states.add(it) })
        fun start() { flow.start(); queue.drain() }
        fun purchase() = PlayPurchaseSubmission(product, token, packageName)
    }

    @Test fun openingReadsRealServerCatalogAndRestoresButNeverBuysOrGrants() {
        val f = Fixture()
        f.start()
        assertEquals(1, f.transport.accountCalls)
        assertEquals(1, f.port.connections)
        assertEquals(1, f.port.restores)
        assertTrue(f.port.launches.isEmpty())
        assertEquals(0, f.transport.submits)
        assertTrue(f.states.none { it.status == PlayBillingStatus.VERIFIED })
        assertEquals(listOf(offer), f.states.last().offers)
    }

    @Test fun deniedOrClosedScopeCannotLoadCatalogOrBuy() {
        val f = Fixture()
        f.allowed = false
        f.start()
        f.flow.buy(offer)
        assertEquals(0, f.transport.accountCalls)
        assertEquals(0, f.port.connections)
        assertTrue(f.port.launches.isEmpty())
        val second = Fixture()
        second.flow.start()
        second.flow.close()
        second.queue.drain()
        assertEquals(0, second.transport.accountCalls)
        assertTrue(second.port.closed)
    }

    @Test fun explicitBuyRefreshesAccountAndLaunchOkIsNeverVerification() {
        val f = Fixture()
        f.start()
        f.flow.buy(offer)
        assertTrue(f.port.launches.isEmpty())
        f.queue.drain()
        assertEquals(2, f.transport.accountCalls)
        assertEquals("a".repeat(64), f.port.launches.single().obfuscatedAccountId)
        assertEquals(PlayBillingStatus.PLAY_OPENED, f.states.last().status)
        assertEquals(0, f.transport.submits)
        assertTrue(f.states.none { it.status == PlayBillingStatus.VERIFIED })
        f.flow.buy(offer)
        f.queue.drain()
        assertEquals(1, f.port.launches.size)
    }

    @Test fun changedScopeOrRemovedServerProductCannotLaunchAfterAsyncFetch() {
        val f = Fixture()
        f.start()
        f.flow.buy(offer)
        f.allowed = false
        f.queue.drain()
        assertTrue(f.port.launches.isEmpty())
        val removed = Fixture()
        removed.start()
        removed.transport.account = PlayAccountConfiguration("b".repeat(64), listOf("other_product"))
        removed.flow.buy(offer)
        removed.queue.drain()
        assertTrue(removed.port.launches.isEmpty())
        assertEquals(PlayBillingStatus.UNAVAILABLE, removed.states.last().status)
    }

    @Test fun invalidServerCatalogNeverConnectsToBilling() {
        for (catalog in listOf(PlayAccountConfiguration("owner", listOf(product)),
                PlayAccountConfiguration("a".repeat(64), emptyList()),
                PlayAccountConfiguration("a".repeat(64), listOf(product, product)))) {
            val f = Fixture()
            f.transport.account = catalog
            f.start()
            assertEquals(0, f.port.connections)
            assertEquals(PlayBillingStatus.UNAVAILABLE, f.states.last().status)
        }
    }

    @Test fun forgedWrongProductOrConflictingOffersAreNotSelectable() {
        val f = Fixture()
        f.port.offers = listOf(offer.copy(productId = "other_product"), offer.copy(pricingPhases = emptyList()))
        f.start()
        assertTrue(f.states.last().offers.isEmpty())
        f.flow.buy(offer)
        assertTrue(f.port.launches.isEmpty())
        val duplicate = Fixture()
        duplicate.port.offers = listOf(offer, offer.copy(displayName = "Conflicting title"))
        duplicate.start()
        assertTrue(duplicate.states.last().offers.isEmpty())
    }

    @Test fun purchaseAndRestoreRequireNewServerProofAndDuplicateCallbacksCoalesce() {
        val f = Fixture()
        f.start()
        f.flow.purchased(f.purchase())
        f.flow.purchased(f.purchase())
        assertEquals(PlayBillingStatus.VERIFYING, f.states.last().status)
        assertEquals(0, f.transport.submits)
        f.queue.drain()
        assertEquals(1, f.transport.submits)
        assertEquals(PlayBillingStatus.VERIFIED, f.states.last().status)
        f.port.restoreCount = 1
        f.port.afterRestore = { f.flow.purchased(f.purchase()) }
        f.flow.refresh()
        f.queue.drain()
        assertEquals(2, f.transport.submits)
        assertEquals(2, f.port.restores)
    }

    @Test fun providerDenialOrFailureNeverBecomesVerified() {
        for (fail in listOf(false, true)) {
            val f = Fixture()
            f.start()
            f.transport.granted = false
            f.transport.fail = fail
            f.flow.purchased(f.purchase())
            f.queue.drain()
            assertEquals(if (fail) PlayBillingStatus.UNAVAILABLE else PlayBillingStatus.DENIED, f.states.last().status)
            assertTrue(f.states.none { it.status == PlayBillingStatus.VERIFIED })
            assertFalse(f.states.toString().contains(token))
        }
    }

    @Test fun mixedRestoredPurchasesAggregateServerProofInEitherCompletionOrder() {
        for (reverse in listOf(false, true)) {
            val f = Fixture()
            val active = f.purchase().copy(purchaseToken = "active-token")
            val expired = f.purchase().copy(purchaseToken = "expired-token")
            f.transport.results[active.purchaseToken] = true
            f.transport.results[expired.purchaseToken] = false
            f.port.restoreCount = 2
            f.port.afterRestore = { f.flow.purchased(active); f.flow.purchased(expired) }
            f.flow.start()
            f.queue.tasks.remove().run() // Account/catalog load schedules both server checks.
            assertEquals(2, f.queue.tasks.size)
            if (reverse) f.queue.tasks.removeLast().run() else f.queue.tasks.removeFirst().run()
            assertEquals(PlayBillingStatus.VERIFYING, f.states.last().status)
            f.queue.drain()
            assertEquals(PlayBillingStatus.VERIFIED, f.states.last().status)
            // A new reconciliation must not reuse that previous success.
            f.transport.results[active.purchaseToken] = false
            f.flow.refresh()
            f.queue.drain()
            assertEquals(PlayBillingStatus.DENIED, f.states.last().status)
        }
    }

    @Test fun unknownProductWrongPackageAndControlTokenNeverReachServer() {
        val f = Fixture()
        f.start()
        for (purchase in listOf(f.purchase().copy(productId = "unconfigured"),
                f.purchase().copy(packageName = "another.app"), f.purchase().copy(purchaseToken = "bad\u0000"))) {
            f.flow.purchased(purchase)
            f.queue.drain()
        }
        assertEquals(0, f.transport.submits)
        assertEquals(PlayBillingStatus.DENIED, f.states.last().status)
    }

    @Test fun pendingCancelAndLateCallbacksDoNotGrantOrReopenClosedUi() {
        val f = Fixture()
        f.start()
        f.flow.pending()
        assertEquals(PlayBillingStatus.PENDING, f.states.last().status)
        f.flow.canceled()
        assertEquals(PlayBillingStatus.CANCELED, f.states.last().status)
        val size = f.states.size
        f.flow.close()
        f.flow.purchased(f.purchase())
        f.flow.pending()
        f.flow.canceled()
        f.queue.drain()
        assertEquals(0, f.transport.submits)
        assertEquals(size, f.states.size)
        val delayed = Fixture()
        delayed.port.delayOffers = true
        delayed.start()
        val before = delayed.states.size
        delayed.flow.close()
        delayed.port.delayedOffer?.invoke(0, listOf(offer))
        assertEquals(before, delayed.states.size)
    }

    @Test fun refreshReconnectsBillingAfterServiceFailure() {
        val f = Fixture()
        f.start()
        f.flow.failed()
        assertEquals(PlayBillingStatus.UNAVAILABLE, f.states.last().status)
        f.flow.refresh()
        f.queue.drain()
        assertEquals(2, f.port.connections)
        assertEquals(2, f.port.restores)
        assertTrue(f.port.launches.isEmpty())
    }
}
