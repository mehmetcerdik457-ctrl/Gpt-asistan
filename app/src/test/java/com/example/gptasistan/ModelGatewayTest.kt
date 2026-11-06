package com.example.gptasistan

import org.junit.Assert.*
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URL
import javax.net.ssl.SSLException

// These are transport-boundary tests with real byte streams, not live AI tests.
class ModelGatewayTest {
    private class TrackedStream(bytes: ByteArray) : ByteArrayInputStream(bytes) {
        var bytesRead = 0
        var closed = false
        override fun read(): Int = super.read().also { if (it >= 0) bytesRead++ }
        override fun read(buffer: ByteArray, offset: Int, length: Int): Int =
            super.read(buffer, offset, length).also { if (it > 0) bytesRead += it }
        override fun close() { closed = true; super.close() }
    }

    private class StubConnection(
        val stream: InputStream,
        private val type: String? = "application/json",
        private val length: Long = -1L,
        private val status: Int = 200
    ) : HttpURLConnection(URL("https://example.invalid/chat")) {
        var opened = false
        var disconnected = false
        val requestBody = ByteArrayOutputStream()
        override fun getContentType(): String? = type
        override fun getContentLengthLong(): Long = length
        override fun getResponseCode(): Int = status
        override fun getOutputStream(): ByteArrayOutputStream = requestBody
        override fun getInputStream(): InputStream { opened = true; return stream }
        override fun connect() = Unit
        override fun disconnect() { disconnected = true }
        override fun usingProxy() = false
    }

    private fun rejected(connection: StubConnection, messageFragment: String) {
        try {
            ModelGateway.readJsonResponse(connection)
            fail("Yanıt reddedilmeliydi")
        } catch (error: ModelGateway.ResponseRejected) {
            assertTrue(error.message.orEmpty(), error.message.orEmpty().contains(messageFragment))
        }
    }

    @Test fun exactByteLimitIsReadWithoutTruncationAndClosed() {
        val body = "\"" + "a".repeat(ModelGateway.MAX_RESPONSE_BYTES - 2) + "\""
        val stream = TrackedStream(body.toByteArray(Charsets.UTF_8))
        assertEquals(body, ModelGateway.readJsonResponse(StubConnection(stream)))
        assertEquals(ModelGateway.MAX_RESPONSE_BYTES, stream.bytesRead)
        assertTrue(stream.closed)
    }

    @Test fun unknownLengthOversizeStopsAfterSingleProbeByte() {
        val stream = TrackedStream(ByteArray(ModelGateway.MAX_RESPONSE_BYTES * 4) { 97 })
        rejected(StubConnection(stream), "boyut sınırını")
        assertEquals(ModelGateway.MAX_RESPONSE_BYTES + 1, stream.bytesRead)
        assertTrue(stream.closed)
    }

    @Test fun misleadingShortDeclaredLengthCannotBypassActualByteLimit() {
        val stream = TrackedStream(ByteArray(ModelGateway.MAX_RESPONSE_BYTES + 100) { 97 })
        rejected(StubConnection(stream, length = 2L), "boyut sınırını")
        assertEquals(ModelGateway.MAX_RESPONSE_BYTES + 1, stream.bytesRead)
        assertTrue(stream.closed)
    }

    @Test fun oversizedDeclaredLengthIsRejectedBeforeOpeningBody() {
        val stream = TrackedStream("{}".toByteArray())
        val connection = StubConnection(stream, length = ModelGateway.MAX_RESPONSE_BYTES.toLong() + 1)
        rejected(connection, "boyut sınırını")
        assertFalse(connection.opened)
        assertEquals(0, stream.bytesRead)
    }

    @Test fun validTurkishUtf8AtByteBoundaryIsPreserved() {
        val body = "\"" + "ğ".repeat((ModelGateway.MAX_RESPONSE_BYTES - 2) / 2) + "\""
        val bytes = body.toByteArray(Charsets.UTF_8)
        assertEquals(ModelGateway.MAX_RESPONSE_BYTES, bytes.size)
        assertEquals(body, ModelGateway.readJsonResponse(StubConnection(TrackedStream(bytes))))
    }

    @Test fun malformedUtf8IsRejectedInsteadOfSilentlyReplaced() {
        val stream = TrackedStream(byteArrayOf(0x22, 0xc3.toByte(), 0x28, 0x22))
        rejected(StubConnection(stream), "geçerli UTF-8 değil")
        assertTrue(stream.closed)
    }

    @Test fun htmlAndMissingContentTypeAreRejectedBeforeBodyRead() {
        for (type in listOf("text/html; charset=utf-8", null)) {
            val connection = StubConnection(TrackedStream("{}".toByteArray()), type = type)
            rejected(connection, "JSON içerik türü")
            assertFalse(connection.opened)
        }
    }

    @Test fun vendorJsonAndQuotedUtf8CharsetAreAccepted() {
        val body = "{\"content\":\"Türkçe: şığöü\"}"
        val connection = StubConnection(
            TrackedStream(body.toByteArray(Charsets.UTF_8)),
            type = "Application/Vnd.Example+Json; Charset=\"UTF-8\""
        )
        assertEquals(body, ModelGateway.readJsonResponse(connection))
    }

    @Test fun unsupportedOrConflictingCharsetIsRejectedBeforeBodyRead() {
        for (type in listOf("application/json; charset=iso-8859-9",
            "application/json; charset=utf-8; charset=latin1", "application/json; charset")) {
            val connection = StubConnection(TrackedStream("{}".toByteArray()), type = type)
            rejected(connection, "UTF-8 olmalı")
            assertFalse(connection.opened)
        }
    }

    @Test fun emptyBodyIsRejectedAndClosed() {
        val stream = TrackedStream(byteArrayOf())
        rejected(StubConnection(stream), "boş yanıt")
        assertTrue(stream.closed)
    }

    @Test fun utf8ByteOrderMarkIsAcceptedWithoutChangingTurkishText() {
        val body = "{\"content\":\"Merhaba Mehmet\"}"
        val stream = TrackedStream(("\uFEFF" + body).toByteArray(Charsets.UTF_8))
        assertEquals(body, ModelGateway.readJsonResponse(StubConnection(stream)))
    }

    @Test fun interruptedReadStillClosesStream() {
        var closed = false
        val stream = object : InputStream() {
            override fun read(): Int = throw IOException("controlled test failure")
            override fun close() { closed = true }
        }
        try {
            ModelGateway.readJsonResponse(StubConnection(stream))
            fail("Okuma hatası iletilmeliydi")
        } catch (_: IOException) {
            assertTrue(closed)
        }
    }

    @Test fun successfulReplyReturnsActualTextAndUsesSingleMessageRequest() {
        val body = "{\"choices\":[{\"message\":{\"content\":\"Merhaba Mehmet\"}}]}"
        val stream = TrackedStream(body.toByteArray(Charsets.UTF_8))
        val connection = StubConnection(stream)
        assertEquals("Merhaba Mehmet", ModelGateway.replyUsingConnection(connection, "test-model", "Selam"))
        val request = org.json.JSONObject(connection.requestBody.toString("UTF-8"))
        assertEquals("test-model", request.getString("model"))
        assertFalse(request.getBoolean("stream"))
        assertEquals(1, request.getJSONArray("messages").length())
        assertEquals("Selam", request.getJSONArray("messages").getJSONObject(0).getString("content"))
        assertEquals("POST", connection.requestMethod)
        assertFalse(connection.instanceFollowRedirects)
        assertEquals("application/json", connection.getRequestProperty("Accept"))
        assertNull(connection.getRequestProperty("Authorization"))
        assertTrue(stream.closed)
        assertTrue(connection.disconnected)
    }

    @Test fun httpErrorsThrowAndNeverReadOrLeakServerBody() {
        val expected = mapOf(401 to ModelGateway.Failure.ACCESS_DENIED,
            403 to ModelGateway.Failure.ACCESS_DENIED, 429 to ModelGateway.Failure.RATE_LIMITED,
            302 to ModelGateway.Failure.REDIRECT, 500 to ModelGateway.Failure.HTTP)
        for ((status, failure) in expected) {
            val connection = StubConnection(TrackedStream("private-server-body".toByteArray()), status = status)
            try {
                ModelGateway.replyUsingConnection(connection, "test-model", "Selam")
                fail("HTTP hatası başarılı model cevabı olamaz")
            } catch (error: ModelGateway.GatewayException) {
                assertEquals(failure, error.failure)
                assertEquals(status, error.httpStatus)
                assertFalse(error.message.orEmpty().contains("private-server-body"))
            }
            assertFalse(connection.opened)
            assertTrue(connection.disconnected)
        }
    }

    @Test fun malformedOrEmptyModelContentNeverReturnsSuccess() {
        val bodies = listOf("not-json", "{}", "{\"choices\":[]}",
            "{\"choices\":[{\"message\":{\"content\":\"\"}}]}",
            "{\"choices\":[{\"message\":{\"content\":\"   \"}}]}",
            "{\"choices\":[{\"message\":{\"content\":null}}]}",
            "{\"choices\":[{\"message\":{\"content\":123}}]}")
        for (body in bodies) {
            val connection = StubConnection(TrackedStream(body.toByteArray(Charsets.UTF_8)))
            try {
                ModelGateway.replyUsingConnection(connection, "test-model", "Selam")
                fail("Boş veya geçersiz model cevabı başarılı olamaz")
            } catch (error: ModelGateway.GatewayException) {
                assertEquals(ModelGateway.Failure.RESPONSE, error.failure)
            }
            assertTrue(connection.disconnected)
        }
    }

    @Test fun timeoutTlsAndNetworkFailuresAreDistinguishedAndDisconnected() {
        val errors = listOf(SocketTimeoutException("private socket detail") to ModelGateway.Failure.TIMEOUT,
            SSLException("private TLS detail") to ModelGateway.Failure.TLS,
            IOException("private network detail") to ModelGateway.Failure.NETWORK)
        for ((exception, failure) in errors) {
            val stream = object : InputStream() { override fun read(): Int = throw exception }
            val connection = StubConnection(stream)
            try {
                ModelGateway.replyUsingConnection(connection, "test-model", "Selam")
                fail("Ağ hatası başarılı model cevabı olamaz")
            } catch (error: ModelGateway.GatewayException) {
                assertEquals(failure, error.failure)
                assertFalse(error.message.orEmpty().contains("private"))
            }
            assertTrue(connection.disconnected)
        }
    }

    @Test fun endpointRejectsQueryCredentialsUserInfoFragmentAndCleartext() {
        for (endpoint in listOf("http://example.invalid/chat",
            "https://user:password@example.invalid/chat", "https://example.invalid/chat#private",
            "https://example.invalid/chat?api_key=private")) {
            assertFalse(endpoint, ModelGateway.valid(endpoint))
        }
        assertTrue(ModelGateway.valid("https://example.invalid:8443/v1/chat/completions"))
    }
}
