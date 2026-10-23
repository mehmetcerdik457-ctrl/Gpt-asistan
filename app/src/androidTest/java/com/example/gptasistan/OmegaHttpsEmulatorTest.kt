package com.example.gptasistan

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.net.HttpURLConnection
import java.net.URL
import java.security.KeyStore
import java.security.cert.CertificateFactory
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManagerFactory
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Emulator HTTPS socket through adb reverse to real OMEGA server. No Owner auth. */
@RunWith(AndroidJUnit4::class)
class OmegaHttpsEmulatorTest {
    private val origin = "https://127.0.0.1:18443"

    private fun testCertOnly(address: URL): HttpURLConnection {
        val testApp = InstrumentationRegistry.getInstrumentation().context
        val cert = testApp.assets.open("omega-ci-loopback-cert.der").use {
            CertificateFactory.getInstance("X.509").generateCertificate(it)
        }
        val store = KeyStore.getInstance(KeyStore.getDefaultType())
        store.load(null)
        store.setCertificateEntry("ephemeral-omega-test-cert", cert)
        val trust = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm())
        trust.init(store)
        val tls = SSLContext.getInstance("TLS")
        tls.init(null, trust.trustManagers, null)
        val conn = address.openConnection() as HttpsURLConnection
        conn.sslSocketFactory = tls.socketFactory
        // Default HTTPS hostname verifier remains active (IP SAN checked).
        return conn
    }

    @Test fun emulatorToOmegaRealTlsIsReadOnly() {
        val observed = OmegaReadOnlyStatus.fetchUsingConnection(origin, ::testCertOnly)
        assertFalse(observed.ownerAccepted)
        assertFalse(observed.executionApproved)
        assertTrue(observed.message.contains("Owner kimlik kanıtı değildir"))
    }

    @Test fun releaseDefaultTrustMustRejectEphemeralCertificate() {
        var denied = false
        try {
            OmegaReadOnlyStatus.fetch(origin)
        } catch (_: Exception) {
            denied = true
        }
        assertTrue("Untrusted CI certificate must fail production default TLS", denied)
    }
}
