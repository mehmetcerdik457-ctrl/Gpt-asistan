package com.example.gptasistan

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL

/** Exercises the shared production request boundary without Keystore or network. */
class OwnerGatewayTransportTest {
    private class Connection(url: URL, private val status: Int, private val payload: String) :
        HttpURLConnection(url) {
        val sent = ByteArrayOutputStream()
        var disconnected = false
        override fun connect() = Unit
        override fun usingProxy() = false
        override fun disconnect() { disconnected = true }
        override fun getOutputStream() = sent
        override fun getResponseCode() = status
        override fun getContentType() = "application/json; charset=utf-8"
        override fun getInputStream() = ByteArrayInputStream(payload.toByteArray(Charsets.UTF_8))
        override fun getErrorStream() = ByteArrayInputStream(payload.toByteArray(Charsets.UTF_8))
    }

    @Test fun rejectsInvalidBaseBeforeSigningOrOpeningConnection() {
        var signingCalls = 0
        var connectionCalls = 0
        assertThrows(IllegalArgumentException::class.java) {
            OwnerGateway.requestUsingTransport("http://fixture.example", OmegaEnvelope.TASKS,
                "fixture-owner", JSONObject(), { _, _, _ ->
                    signingCalls++
                    emptyMap()
                }, {
                    connectionCalls++
                    Connection(it, 200, "{}")
                })
        }
        assertEquals(0, signingCalls)
        assertEquals(0, connectionCalls)
    }

    @Test fun transmitsTheExactUtf8BodyThatWasSignedWithBoundPathAndOwner() {
        val connection = Connection(URL("https://fixture.example" + OmegaEnvelope.TASKS),
            200, """{"contract":"OMEGA-OWNER-API-V1","accepted":true}""")
        val json = JSONObject().put("input", "Türkçe görev: ğüşiöç")
        var signedBody: ByteArray? = null
        val reply = OwnerGateway.requestUsingTransport("https://fixture.example/", OmegaEnvelope.TASKS,
            "fixture-owner", json, { path, body, owner ->
                assertEquals(OmegaEnvelope.TASKS, path)
                assertEquals("fixture-owner", owner)
                signedBody = body.copyOf()
                mapOf("X-Omega-Owner-Proof" to "synthetic-proof")
            }, { url ->
                assertEquals("https://fixture.example" + OmegaEnvelope.TASKS, url.toString())
                connection
            })
        assertTrue(reply.getBoolean("accepted"))
        assertArrayEquals(signedBody, connection.sent.toByteArray())
        assertEquals(json.toString(), connection.sent.toString("UTF-8"))
        assertEquals("POST", connection.requestMethod)
        assertEquals("synthetic-proof", connection.getRequestProperty("X-Omega-Owner-Proof"))
        assertNull(connection.getRequestProperty("Authorization"))
        assertFalse(connection.instanceFollowRedirects)
        assertEquals(8000, connection.connectTimeout)
        assertEquals(45000, connection.readTimeout)
        assertTrue(connection.disconnected)
    }

    @Test fun typedFailureUsesOnlyTheRedactedErrorContractAndAlwaysDisconnects() {
        val connection = Connection(URL("https://fixture.example" + OmegaEnvelope.CHAT), 502,
            """{"error":"PROVIDER_AUTH_DENIED","provider_http_status":401,
                "provider_request_id":"req_fixture_401","retryable":false,
                "message":"PRIVATE_UPSTREAM_MESSAGE","key":"SYNTHETIC_SECRET"}""")
        val failure = assertThrows(OwnerGateway.GatewayFailure::class.java) {
            OwnerGateway.requestUsingTransport("https://fixture.example", OmegaEnvelope.CHAT,
                "fixture-owner", JSONObject(), { _, _, _ -> emptyMap() }, { connection })
        }
        assertEquals("PROVIDER_AUTH_DENIED", failure.errorCode)
        assertEquals(401, failure.providerHttpStatus)
        assertEquals("req_fixture_401", failure.providerRequestId)
        assertEquals("PROVIDER_AUTH_DENIED", failure.message)
        assertFalse(failure.toString().contains("PRIVATE_UPSTREAM_MESSAGE"))
        assertFalse(failure.toString().contains("SYNTHETIC_SECRET"))
        assertTrue(connection.disconnected)
    }
}
