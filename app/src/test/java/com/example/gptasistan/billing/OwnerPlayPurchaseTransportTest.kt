package com.example.gptasistan.billing

import android.content.Context
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.util.concurrent.atomic.AtomicReference

/** Guards fail before any HTTP/signing operation; no network or real Keystore is used. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class OwnerPlayPurchaseTransportTest {
    @Test fun mainThreadIsRejectedBeforeAnyAccountOrVerificationRequest() {
        val context = RuntimeEnvironment.getApplication()
        val transport = OwnerPlayPurchaseTransport(context, "https://gateway.example", "owner-test")
        try {
            transport.account()
            fail("main thread was accepted")
        } catch (expected: IllegalStateException) { assertEquals("PLAY_WORKER_REQUIRED", expected.message) }
    }

    @Test fun changedBackendIdentityIsRejectedOnWorkerBeforeSigningOrHttp() {
        val context = RuntimeEnvironment.getApplication()
        val prefs = context.getSharedPreferences("kral_model", Context.MODE_PRIVATE)
        prefs.edit().clear().putString("endpoint", "https://other.example")
            .putString("owner_id", "different-owner").commit()
        val caught = AtomicReference<Throwable?>()
        val transport = OwnerPlayPurchaseTransport(context, "https://gateway.example", "owner-test")
        val worker = Thread {
            try { transport.account() } catch (error: Throwable) { caught.set(error) }
        }
        try {
            worker.start()
            worker.join(2000)
            assertFalse("worker must fail before networking", worker.isAlive)
            assertTrue(caught.get() is IllegalStateException)
            assertEquals("PLAY_BACKEND_SCOPE_CHANGED", caught.get()?.message)
        } finally { prefs.edit().clear().commit() }
    }
}
