package com.example.gptasistan

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class OwnerPlayGatewayTest {
    private val prefix = OmegaEnvelope.CONTRACT

    @Test fun accountPathIsSignedAndBoundToBodyBytes() {
        val raw = "{}".toByteArray(Charsets.UTF_8)
        val canonical = OmegaEnvelope.canonical(
            OmegaEnvelope.PLAY_ACCOUNT, raw, "1794000000",
            "a".repeat(48), "owner-test", "b".repeat(64),
        ).toString(Charsets.UTF_8)
        assertTrue(canonical.contains("/api/v1/owner/play/account"))
        assertTrue(canonical.contains(OmegaEnvelope.sha256(raw)))
        assertTrue(canonical.startsWith(prefix))
    }

    @Test fun verifyPathIsSignedAndBoundToTokenPayloadHash() {
        val first = """{"productId":"orba_pro_monthly","purchaseToken":"first"}"""
        val second = """{"productId":"orba_pro_monthly","purchaseToken":"second"}"""
        fun canonical(payload: String) = OmegaEnvelope.canonical(
            OmegaEnvelope.PLAY_VERIFY, payload.toByteArray(), "1794000000",
            "a".repeat(48), "owner-test", "b".repeat(64)
        ).toList()
        assertFalse(canonical(first) == canonical(second))
    }

    @Test fun unauthorizedRouteIsNotSignable() {
        try {
            OmegaEnvelope.canonical("/api/v1/owner/play/admin",
                "{}".toByteArray(), "1794000000", "a".repeat(48),
                "owner-test", "b".repeat(64))
            throw AssertionError("unknown route unexpectedly allowed")
        } catch (_: IllegalArgumentException) {
            // Expected failure before accessing Android Keystore
        }
    }

    @Test fun parsesValidServerObfuscatedAccountId() {
        val p = JSONObject().put("contract", prefix)
            .put("obfuscated_account_id", "a".repeat(64))
        assertEquals("a".repeat(64), OwnerGateway.parsePlayAccountId(p))
    }

    @Test fun rejectsRawOwnerEmailAsPlayAccountId() {
        val p = JSONObject().put("contract", prefix)
            .put("obfuscated_account_id", "owner@example.com")
        try {
            OwnerGateway.parsePlayAccountId(p)
            throw AssertionError("raw owner ID accepted")
        } catch (_: IllegalArgumentException) { }
    }

    @Test fun rejectsMalformedAccountId() {
        val p = JSONObject().put("contract", prefix)
            .put("obfuscated_account_id", "F".repeat(64))
        try {
            OwnerGateway.parsePlayAccountId(p)
            throw AssertionError("noncanonical obfuscated account accepted")
        } catch (_: IllegalArgumentException) { }
    }

    @Test fun parsesConfirmedEntitlement() {
        val p = JSONObject().put("contract", prefix)
            .put("entitled", true).put("verified_by", "server_google_play")
        assertTrue(OwnerGateway.parsePlayEntitlement(p))
    }

    @Test fun parsesDeniedEntitlement() {
        val p = JSONObject().put("contract", prefix)
            .put("entitled", false).put("verified_by", "denied")
        assertFalse(OwnerGateway.parsePlayEntitlement(p))
    }

    @Test fun rejectsHTTP200WithoutEntitlementProof() {
        val p = JSONObject().put("contract", prefix).put("status", "ok")
        try {
            OwnerGateway.parsePlayEntitlement(p)
            throw AssertionError("HTTP 200 treated as grant")
        } catch (_: Exception) { }
    }

    @Test fun rejectsClientForgedVerifiedFlag() {
        val p = JSONObject().put("contract", prefix)
            .put("entitled", true).put("verified_by", "client")
        try {
            OwnerGateway.parsePlayEntitlement(p)
            throw AssertionError("client proof accepted")
        } catch (_: IllegalArgumentException) { }
    }

    @Test fun rejectsEntitlementContradiction() {
        val p = JSONObject().put("contract", prefix)
            .put("entitled", false).put("verified_by", "server_google_play")
        try {
            OwnerGateway.parsePlayEntitlement(p)
            throw AssertionError("contradictory response accepted")
        } catch (_: IllegalArgumentException) { }
    }
}
