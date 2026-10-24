package com.example.gptasistan

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** Pure wire contract; never connects to Owner, Google or AI providers. */
class OwnerSourceListTest {
    private fun response(): JSONObject {
        val row = JSONObject()
            .put("source_id", "archive/old.apk")
            .put("format_hint", "android_apk")
            .put("size_bytes", 123L)
        return JSONObject()
            .put("contract", OmegaEnvelope.CONTRACT)
            .put("read_only", true)
            .put("capability_status", "UNTESTED")
            .put("integration_status", "NOT_CONNECTED")
            .put("truncated", false)
            .put("sources", JSONArray().put(row))
    }

    @Test fun validSourceListDoesNotClaimExecution() {
        val parsed = OwnerSourceInspection.parseSourceList(response())
        assertEquals(1, parsed.entries.size)
        assertEquals("archive/old.apk", parsed.entries.single().sourceId)
        assertFalse(parsed.truncated)
        assertTrue(parsed.entries.single().label().contains("123 bayt"))
    }

    @Test fun truncatedListRemainsExplicit() {
        val parsed = OwnerSourceInspection.parseSourceList(response().put("truncated", true))
        assertTrue(parsed.truncated)
        assertEquals(1, parsed.entries.size)
    }

    @Test fun deniesUnsignedOrUpgradedCapabilities() {
        for ((key, invalid) in listOf(
            "read_only" to false,
            "capability_status" to "TESTED",
            "integration_status" to "CONNECTED",
            "contract" to "WRONG",
            "truncated" to "false"
        )) {
            val data = response().put(key, invalid)
            assertThrows(IllegalArgumentException::class.java) {
                OwnerSourceInspection.parseSourceList(data)
            }
        }
    }

    @Test fun deniesTraversalSecretsAndUnsupportedSources() {
        for (sourceId in listOf("../escape.apk", "secrets/private.apk",
                ".hidden.apk", "notes.txt", "model.p12")) {
            val data = response()
            data.getJSONArray("sources").getJSONObject(0).put("source_id", sourceId)
            assertThrows(IllegalArgumentException::class.java) {
                OwnerSourceInspection.parseSourceList(data)
            }
        }
    }

    @Test fun rejectsOversizedNegativeAndFakeAmounts() {
        for (bad in listOf(-1, 134217729, "100", true)) {
            val data = response()
            data.getJSONArray("sources").getJSONObject(0).put("size_bytes", bad)
            assertThrows(IllegalArgumentException::class.java) {
                OwnerSourceInspection.parseSourceList(data)
            }
        }
    }

    @Test fun preventsDuplicateSourceIdsAndTooManyEntries() {
        val data = response()
        data.getJSONArray("sources").put(JSONObject()
            .put("source_id", "archive/old.apk")
            .put("format_hint", "android_apk")
            .put("size_bytes", 12L))
        assertThrows(IllegalArgumentException::class.java) {
            OwnerSourceInspection.parseSourceList(data)
        }
        val longList = response()
        val array = longList.getJSONArray("sources")
        for (i in 1..50) {
            array.put(JSONObject().put("source_id", "item${i}.apk")
                .put("format_hint", "android_apk").put("size_bytes", 1))
        }
        assertThrows(IllegalArgumentException::class.java) {
            OwnerSourceInspection.parseSourceList(longList)
        }
    }
}
