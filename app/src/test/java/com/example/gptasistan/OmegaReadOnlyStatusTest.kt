package com.example.gptasistan

import java.io.ByteArrayInputStream
import java.net.HttpURLConnection
import java.net.URL
import org.junit.Assert.*
import org.junit.Test

/** Real OMEGA /api/health wire format, but synthetic transport (no network). */
class OmegaReadOnlyStatusTest {
    private class FakeConnection(
        private val json: String,
        private val status: Int = 200,
        private val mime: String = "application/json"
    ) : HttpURLConnection(URL("https://omega.example.test/api/health")) {
        override fun connect() {}
        override fun disconnect() {}
        override fun usingProxy() = false
        override fun getResponseCode() = status
        override fun getContentType() = mime
        override fun getInputStream() = ByteArrayInputStream(json.toByteArray(Charsets.UTF_8))
    }

    private fun health(owner: String = "false", execution: String = "false") =
        """{"status":"PASS","version":"P1_BACKEND_ONLY","provider_configured":true,"owner_identity_verified":$owner,"execution_enabled":$execution}"""

    @Test fun acceptsOnlyNonExecutingUnprovisionedStatusAsStatusNotProof() {
        val s = OmegaReadOnlyStatus.verifyHealth(FakeConnection(health()))
        assertFalse(s.ownerAccepted)
        assertFalse(s.executionApproved)
        assertTrue(s.message.contains("Owner kimlik kanıtı değildir"))
    }

    @Test fun deniesClaimedExecutionOrOwnerBeforePresentingAsAccepted() {
        for (payload in listOf(health("true"), health(execution = "true"),
            health("true", "true"), health("\"false\""), health(execution = "\"false\""),
            """{"status":"PASS","execution_enabled":false}""",
            """{"status":"PASS","owner_identity_verified":false}""",
            """{"status":"FAILED","owner_identity_verified":false,"execution_enabled":false}""",
            """{}""", """[]""")) {
            assertThrows(Exception::class.java) {
                OmegaReadOnlyStatus.verifyHealth(FakeConnection(payload))
            }
        }
    }

    @Test fun rejectsOversizeRedirectWrongContentTypeAndHttpError() {
        for (conn in listOf(
            FakeConnection(health(), 302),
            FakeConnection(health(), 503),
            FakeConnection(health(), 200, "text/html"),
            FakeConnection(health() + " ".repeat(4097)))) {
            assertThrows(Exception::class.java) { OmegaReadOnlyStatus.verifyHealth(conn) }
        }
    }

    @Test fun validatesStrictHttpsRootAndNeverAcceptsCredentialsOrQuery() {
        assertTrue(OmegaReadOnlyStatus.validBase("https://omega.example.test"))
        assertTrue(OmegaReadOnlyStatus.validBase("https://omega.example.test:8443/"))
        for (url in listOf("http://omega.example.test", "https://a:b@omega.example.test",
            "https://omega.example.test/api/health", "https://omega.example.test/?secret=x",
            "https://omega.example.test/#test", "https://omega.example.test:0")) {
            assertFalse(url, OmegaReadOnlyStatus.validBase(url))
        }
    }
}
