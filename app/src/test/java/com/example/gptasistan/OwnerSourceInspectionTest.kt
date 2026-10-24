package com.example.gptasistan

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** No network or Owner signing: these are fail-closed wire contract tests. */
class OwnerSourceInspectionTest {
    private val sourceId = "old/reference.apk"
    private fun valid(): JSONObject {
        val structure = JSONObject()
            .put("status", "ZIP_STRUCTURE_VERIFIED")
            .put("signature_verified", false)
            .put("install_tested", false)
            .put("model_inference_tested", false)
            .put("dex_count", 3)
            .put("native_library_count", 4)
            .put("native_abis", JSONArray().put("arm64-v8a").put("x86_64"))
        return JSONObject().put("contract", OmegaEnvelope.CONTRACT)
            .put("source", JSONObject()
                .put("source_id", sourceId)
                .put("size_bytes", 199)
                .put("sha256", "a".repeat(64))
                .put("format_hint", "android_apk")
                .put("status", "ANALYZED_STATIC")
                .put("read_only", true)
                .put("capability_status", "UNTESTED")
                .put("integration_status", "NOT_CONNECTED")
                .put("apk_structure", structure))
    }

    @Test fun pathMatchesExactOwnerSignedRoute() {
        val canonical = OmegaEnvelope.canonical(
            OmegaEnvelope.SOURCES, "{\"action\":\"inspect\"}".toByteArray(),
            "1792537200", "b".repeat(48), "Mehmet", "a".repeat(64))
        assertTrue(String(canonical).contains("/api/v1/owner/sources"))
        assertThrows(IllegalArgumentException::class.java) {
            OmegaEnvelope.canonical("/api/v1/owner/admin", "{}".toByteArray(),
                "1792537200", "b".repeat(48), "Mehmet", "a".repeat(64))
        }
    }

    @Test fun blocksTraversalSecretsAndUnsupportedFormatsBeforeNetwork() {
        listOf("", "../a.apk", "/a.apk", "sub/../a.apk", "sub//a.apk",
            ".git/config.json", "secrets/key.apk", "file.pem",
            "a\\b.apk", "id_rsa", "example.txt", "config.env",
            "a.apk\n", "nested/.hidden.apk").forEach {
            assertFalse(it, OwnerSourceInspection.validSourceId(it))
        }
        assertTrue(OwnerSourceInspection.validSourceId(sourceId))
        assertTrue(OwnerSourceInspection.validSourceId("model/model.gguf"))
    }

    @Test fun acceptsBoundedStaticEvidenceWithoutClaimingExecution() {
        val found = OwnerSourceInspection.parseEvidence(valid(), sourceId)
        assertEquals("ANALYZED_STATIC", found.staticStatus)
        assertEquals(3, found.structure?.dexCount)
        assertEquals(4, found.structure?.nativeCount)
        assertTrue(found.report().contains("doğrulanmış DEĞİLDİR"))
        assertFalse(found.report().contains("MODEL ÇALIŞIYOR"))
    }

    @Test fun rejectsMisboundFileContractOrOwnerStatus() {
        assertThrows(IllegalArgumentException::class.java) {
            OwnerSourceInspection.parseEvidence(valid(), "other.apk")
        }
        assertThrows(IllegalArgumentException::class.java) {
            OwnerSourceInspection.parseEvidence(valid().put("contract", "FAKE"), sourceId)
        }
        for (key in listOf("read_only", "capability_status", "integration_status")) {
            val item = valid()
            item.getJSONObject("source").put(key, "CONNECTED")
            assertThrows(IllegalArgumentException::class.java) {
                OwnerSourceInspection.parseEvidence(item, sourceId)
            }
        }
    }

    @Test fun rejectsFalseUnsignedZipClaimsAndServerArbitraryMetadata() {
        for ((key, bad) in listOf(
            "signature_verified" to true, "install_tested" to true,
            "model_inference_tested" to true, "dex_count" to -1,
            "native_library_count" to "one"
        )) {
            val item = valid()
            item.getJSONObject("source").getJSONObject("apk_structure").put(key, bad)
            assertThrows(IllegalArgumentException::class.java) {
                OwnerSourceInspection.parseEvidence(item, sourceId)
            }
        }
        val changedHash = valid()
        changedHash.getJSONObject("source").put("sha256", "not_sha")
        assertThrows(IllegalArgumentException::class.java) {
            OwnerSourceInspection.parseEvidence(changedHash, sourceId)
        }
    }

    @Test fun blockedApkRemainsVisibleAsUnverifiedStructure() {
        val item = valid()
        item.getJSONObject("source").put("status", "VERIFIED_FILE")
            .getJSONObject("apk_structure").put("status", "BLOCKED")
        val report = OwnerSourceInspection.parseEvidence(item, sourceId)
        assertEquals("BLOCKED", report.structure?.status)
        assertNull(OwnerSourceInspection.parseEvidence(
            JSONObject().put("contract", OmegaEnvelope.CONTRACT)
                .put("source", JSONObject()
                    .put("source_id", "notes.md").put("size_bytes", 12)
                    .put("sha256", "a".repeat(64)).put("format_hint", "markdown_document")
                    .put("status", "VERIFIED_FILE").put("read_only", true)
                    .put("capability_status", "UNTESTED")
                    .put("integration_status", "NOT_CONNECTED")), "notes.md").structure)
    }
}
