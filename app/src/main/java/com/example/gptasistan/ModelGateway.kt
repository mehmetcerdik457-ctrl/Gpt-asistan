package com.example.gptasistan

import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URL
import java.nio.ByteBuffer
import java.nio.charset.CharacterCodingException
import java.nio.charset.CodingErrorAction
import java.util.Locale
import javax.net.ssl.SSLException

// User-configured HTTPS OpenAI-compatible model endpoint. No credentials or
// memories are sent automatically. No redirect, no cleartext, no tool execution.
object ModelGateway {
    internal const val MAX_RESPONSE_BYTES = 131072

    internal enum class Failure { ACCESS_DENIED, RATE_LIMITED, REDIRECT, HTTP, RESPONSE, TIMEOUT, TLS, NETWORK }

    internal open class GatewayException(
        val failure: Failure,
        message: String,
        val httpStatus: Int? = null
    ) : IOException(message)

    internal class ResponseRejected(message: String) : GatewayException(Failure.RESPONSE, message)

    fun valid(endpoint: String): Boolean = try {
        val u = URL(endpoint)
        u.protocol == "https" && !u.host.isNullOrBlank() &&
            u.userInfo == null && u.ref == null && u.query == null && u.port in -1..65535
    } catch (_: Exception) { false }

    fun reply(endpoint: String, model: String, question: String): String {
        require(valid(endpoint)) { "Yalnız HTTPS model bağlantısı desteklenir." }
        require(model.isNotBlank()) { "Model adı gerekli." }
        val connection = try {
            URL(endpoint).openConnection() as HttpURLConnection
        } catch (_: IOException) {
            throw GatewayException(Failure.NETWORK, "Model sunucusuna bağlantı açılamadı.")
        }
        return replyUsingConnection(connection, model, question)
    }

    // Internal seam for transport tests. Production callers always pass through
    // reply(), which validates the user-configured HTTPS endpoint first.
    internal fun replyUsingConnection(c: HttpURLConnection, model: String, question: String): String {
        return try {
            c.requestMethod = "POST"
            c.connectTimeout = 8000
            c.readTimeout = 30000
            c.instanceFollowRedirects = false
            c.doOutput = true
            c.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            c.setRequestProperty("Accept", "application/json")
            val body = JSONObject()
                .put("model", model)
                .put("stream", false)
                .put("messages", JSONArray().put(JSONObject()
                    .put("role", "user").put("content", question)))
                .toString()
            c.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            when (val status = c.responseCode) {
                200 -> {
                    val response = readJsonResponse(c)
                    val content = JSONObject(response).getJSONArray("choices").getJSONObject(0)
                        .getJSONObject("message").get("content")
                    if (content !is String || content.isBlank()) {
                        throw ResponseRejected("Model sunucusu geçerli bir metin yanıtı göndermedi.")
                    }
                    content.take(8000)
                }
                401, 403 -> throw GatewayException(Failure.ACCESS_DENIED,
                    "Model sunucusu erişimi reddetti (HTTP $status).", status)
                429 -> throw GatewayException(Failure.RATE_LIMITED,
                    "Model sunucusunun kullanım sınırına ulaşıldı (HTTP 429).", status)
                in 300..399 -> throw GatewayException(Failure.REDIRECT,
                    "Model sunucusu yönlendirme istedi; yönlendirme izlenmedi (HTTP $status).", status)
                else -> throw GatewayException(Failure.HTTP,
                    "Model yanıtı alınamadı (HTTP $status).", status)
            }
        } catch (error: GatewayException) {
            throw error
        } catch (_: SocketTimeoutException) {
            throw GatewayException(Failure.TIMEOUT, "Model bağlantısı zaman aşımına uğradı.")
        } catch (_: SSLException) {
            throw GatewayException(Failure.TLS, "Model sunucusuyla güvenli HTTPS bağlantısı kurulamadı.")
        } catch (_: JSONException) {
            throw ResponseRejected("Model sunucusu beklenen JSON sohbet yanıtını göndermedi.")
        } catch (_: IOException) {
            throw GatewayException(Failure.NETWORK, "Model sunucusuna ulaşılamadı veya yanıt okunamadı.")
        } finally { c.disconnect() }
    }

    // Enforce the limit while reading, including responses without a declared
    // length. Never parse a truncated response or include its body in an error.
    internal fun readJsonResponse(connection: HttpURLConnection): String {
        val parts = connection.contentType.orEmpty().split(';')
        val mediaType = parts.first().trim().lowercase(Locale.ROOT)
        if (mediaType != "application/json" &&
            !(mediaType.startsWith("application/") && mediaType.endsWith("+json"))) {
            throw ResponseRejected("Model sunucusu JSON içerik türü göndermedi.")
        }
        val charsetParameters = parts.drop(1).map { it.trim() }.filter {
            it.substringBefore('=').trim().equals("charset", ignoreCase = true)
        }
        for (parameter in charsetParameters) {
            val charset = parameter.substringAfter('=', "").trim().removeSurrounding("\"")
            if (!charset.equals("utf-8", ignoreCase = true) &&
                !charset.equals("utf8", ignoreCase = true)) {
                throw ResponseRejected("Model sunucusunun JSON yanıtı UTF-8 olmalı.")
            }
        }
        if (connection.contentLengthLong > MAX_RESPONSE_BYTES) {
            throw ResponseRejected("Model sunucusunun yanıtı boyut sınırını aştı.")
        }

        val bytes = connection.inputStream.use { input ->
            val output = ByteArrayOutputStream()
            val buffer = ByteArray(8192)
            var total = 0
            while (true) {
                // One extra byte distinguishes an exact-limit response from an
                // oversized one without consuming the rest of the stream.
                val count = input.read(buffer, 0, minOf(buffer.size, MAX_RESPONSE_BYTES - total + 1))
                if (count < 0) break
                if (count == 0) {
                    val next = input.read()
                    if (next < 0) break
                    total++
                    if (total > MAX_RESPONSE_BYTES) {
                        throw ResponseRejected("Model sunucusunun yanıtı boyut sınırını aştı.")
                    }
                    output.write(next)
                } else {
                    total += count
                    if (total > MAX_RESPONSE_BYTES) {
                        throw ResponseRejected("Model sunucusunun yanıtı boyut sınırını aştı.")
                    }
                    output.write(buffer, 0, count)
                }
            }
            output.toByteArray()
        }
        if (bytes.isEmpty()) throw ResponseRejected("Model sunucusu boş yanıt gönderdi.")
        return try {
            Charsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes)).toString().removePrefix("\uFEFF")
        } catch (_: CharacterCodingException) {
            throw ResponseRejected("Model sunucusunun yanıtı geçerli UTF-8 değil.")
        }
    }
}
