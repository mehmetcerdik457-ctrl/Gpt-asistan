package com.example.gptasistan

import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale
import org.json.JSONObject

/**
 * Public OMEGA status bridge. GET ONLY, no Owner keys, tokens, model routing,
 * history upload or privileged operations. It never grants authentication.
 */
object OmegaReadOnlyStatus {
    private const val MAX_BYTES = 4096

    data class Observation(val message: String, val ownerAccepted: Boolean = false,
                           val executionApproved: Boolean = false)

    fun validBase(base: String) = OwnerGateway.validBase(base)

    /** Parser seam for deterministic isolated JVM tests. Caller owns disconnect(). */
    internal fun verifyHealth(connection: HttpURLConnection): Observation {
        require(connection.responseCode == 200) { "OMEGA_STATUS_UNAVAILABLE" }
        require(connection.contentType.orEmpty().substringBefore(';')
            .trim().lowercase(Locale.ROOT) == "application/json") {
            "OMEGA_STATUS_TYPE_DENIED"
        }
        val bytes = ByteArrayOutputStream()
        val block = ByteArray(512)
        connection.inputStream.use { input ->
            while (true) {
                val count = input.read(block)
                if (count < 0) break
                require(bytes.size() + count <= MAX_BYTES) { "OMEGA_STATUS_OVERSIZE" }
                if (count > 0) bytes.write(block, 0, count)
            }
        }
        val payload = JSONObject(bytes.toString("UTF-8"))
        require(payload.opt("status") == "PASS") { "OMEGA_STATUS_UNTRUSTED" }
        // This is an unauthenticated health endpoint; even a 'true' cannot
        // authenticate a real Owner. Fail closed instead of displaying 'ready'.
        require(payload.opt("owner_identity_verified") === false
            && payload.opt("execution_enabled") === false) { "OMEGA_STATUS_UNTRUSTED" }
        return Observation("OMEGA HTTPS durum yanıtı alındı. Sunucunun bildirdiği: " +
            "Owner doğrulanmamış, yürütme kapalı. Bu bir Owner kimlik kanıtı değildir.")
    }

    fun fetch(base: String): Observation {
        require(validBase(base)) { "OMEGA_URL_DENIED" }
        val connection = (URL(base.trimEnd('/') + "/api/health").openConnection()
            as HttpURLConnection)
        return try {
            connection.requestMethod = "GET"
            connection.instanceFollowRedirects = false
            connection.connectTimeout = 5000
            connection.readTimeout = 5000
            connection.setRequestProperty("Accept", "application/json")
            verifyHealth(connection)
        } finally {
            connection.disconnect()
        }
    }
}
