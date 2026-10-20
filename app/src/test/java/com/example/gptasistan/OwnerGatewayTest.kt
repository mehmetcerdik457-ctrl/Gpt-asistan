package com.example.gptasistan

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** Wire/parser tests only. Fixtures are not live provider or Keystore evidence. */
class OwnerGatewayTest {
    private val now = 1792537200L
    private fun modelJson() = JSONObject().put("contract", OmegaEnvelope.CONTRACT)
        .put("models", org.json.JSONArray().put(JSONObject().put("id", "returned-model")
            .put("provider", "openai").put("verified_at", now).put("latency_ms", 23)))

    @Test fun rejectsCredentialsQueriesAndNonRootUrlsBeforeSigning() {
        assertTrue(OwnerGateway.validBase("https://server.example"))
        assertTrue(OwnerGateway.validBase("https://server.example:8443/"))
        listOf("http://server.example", "https://secret@server.example", "https://server.example/?token=secret",
            "https://server.example/api/chat", "https://server.example/#fragment", "https://server.example:0").forEach {
            assertFalse(it, OwnerGateway.validBase(it))
        }
    }

    @Test fun registryRequiresFreshTypedVerificationAndUniqueProviderReturnedIds() {
        assertEquals("returned-model", OwnerGateway.parseModels(modelJson(), now).single().id)
        for (field in listOf("verified_at", "latency_ms")) {
            val value = modelJson()
            value.getJSONArray("models").getJSONObject(0).put(field, "123")
            assertThrows(IllegalArgumentException::class.java) { OwnerGateway.parseModels(value, now) }
        }
        val stale = modelJson()
        stale.getJSONArray("models").getJSONObject(0).put("verified_at", now - 301)
        assertThrows(IllegalArgumentException::class.java) { OwnerGateway.parseModels(stale, now) }
        val duplicate = modelJson()
        duplicate.getJSONArray("models").put(duplicate.getJSONArray("models").getJSONObject(0))
        assertThrows(IllegalArgumentException::class.java) { OwnerGateway.parseModels(duplicate, now) }
        val wrongContract = modelJson().put("contract", "private-omega")
        assertThrows(IllegalArgumentException::class.java) { OwnerGateway.parseModels(wrongContract, now) }
    }

    @Test fun replyMustReportSelectedProviderAndModelWithNonemptyText() {
        val model = OwnerGateway.Model("returned-model", "openai", now, 23)
        fun response() = JSONObject().put("contract", OmegaEnvelope.CONTRACT).put("model", model.id)
            .put("provider", model.provider).put("latency_ms", 50).put("text", "Merhaba Mehmet")
        assertEquals("Merhaba Mehmet", OwnerGateway.parseReply(response(), model))
        listOf(response().put("model", "requested-alias"), response().put("provider", "different-provider"),
            response().put("text", " "), response().put("text", 42), response().put("latency_ms", -1)).forEach {
            assertThrows(IllegalArgumentException::class.java) { OwnerGateway.parseReply(it, model) }
        }
    }

    @Test fun canonicalBindsExactBytesPathOwnerDeviceAndTimestamp() {
        val body = "{}".toByteArray()
        val device = "a".repeat(64)
        val nonce = "b".repeat(48)
        val canonical = OmegaEnvelope.canonical(OmegaEnvelope.CHAT, body, "1792537200", nonce, "Mehmet", device)
        assertEquals("OMEGA-OWNER-API-V1\nPOST\n/api/v1/owner/chat\n" +
            "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a\n" +
            "1792537200\n$nonce\nMehmet\n$device", canonical.toString(Charsets.UTF_8))
        assertFalse(canonical.contentEquals(OmegaEnvelope.canonical(OmegaEnvelope.MODELS, body, "1792537200", nonce, "Mehmet", device)))
        assertFalse(canonical.contentEquals(OmegaEnvelope.canonical(OmegaEnvelope.CHAT, "{ }".toByteArray(), "1792537200", nonce, "Mehmet", device)))
        assertThrows(IllegalArgumentException::class.java) {
            OmegaEnvelope.canonical("/api/v1/owner/delete", body, "1792537200", nonce, "Mehmet", device)
        }
        assertThrows(IllegalArgumentException::class.java) {
            OmegaEnvelope.canonical(OmegaEnvelope.CHAT, body, "1792537200", nonce, "Mehmet\nOther", device)
        }
    }

    @Test fun noModelsAreVerifiedAtProcessStart() {
        OwnerGateway.clear()
        assertTrue(OwnerGateway.verifiedModels("https://server.example", "Mehmet").isEmpty())
    }
}
