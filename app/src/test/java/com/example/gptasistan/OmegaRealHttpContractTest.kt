package com.example.gptasistan

import java.io.ByteArrayInputStream
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test

/** Kotlin consumes actual pinned OMEGA server HTTP bytes, CI loopback only. */
class OmegaRealHttpContractTest {
    private class CapturedConnection(val body: ByteArray) :
        HttpURLConnection(URL("https://omega-contract.example.invalid/api/health")) {
        override fun connect() {}
        override fun disconnect() {}
        override fun usingProxy() = false
        override fun getResponseCode() = 200
        override fun getContentType() = "application/json; charset=utf-8"
        override fun getInputStream() = ByteArrayInputStream(body)
    }

    @Test fun actualPinnedOmegaHealthIsReadOnlyNotOwnerAuthorization() {
        val path = System.getenv("KRAL_OMEGA_REAL_HTTP_DIR")
        assumeTrue("Only active in dedicated cross-repo CI job", !path.isNullOrBlank())
        val bytes = File(path, "health.json").readBytes()
        val evidence = JSONObject(File(path, "evidence.json").readText(Charsets.UTF_8))
        assertEquals("fd34e1a6b57b13644c6f2053fe97e86b485de10b", evidence.getString("source_sha"))
        assertEquals("real_loopback_http", evidence.getString("transport"))
        val digest = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") {
            "%02x".format(it.toInt() and 255)
        }
        assertEquals(digest, evidence.getString("health_sha256"))
        assertEquals(403, evidence.getInt("models_http_status"))
        assertEquals(403, evidence.getInt("chat_http_status"))
        assertFalse(evidence.getBoolean("tls_tested"))
        assertFalse(evidence.getBoolean("android_physical_device_tested"))
        assertFalse(evidence.getBoolean("owner_enrolled"))
        assertFalse(evidence.getBoolean("execution_approved"))
        val status = OmegaReadOnlyStatus.verifyHealth(CapturedConnection(bytes))
        assertFalse(status.ownerAccepted)
        assertFalse(status.executionApproved)
        assertTrue(status.message.contains("Owner kimlik kanıtı değildir"))
    }
}
