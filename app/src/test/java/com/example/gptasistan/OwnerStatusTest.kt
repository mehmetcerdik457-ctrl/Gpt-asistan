package com.example.gptasistan

import org.junit.Assert.*
import org.junit.Test

class OwnerStatusTest {
    private val signer = OwnerStatus.GEN2_CERT_SHA256
    @Test fun correctVersionsRequireOriginalGen2Signer() {
        assertEquals(OwnerStatus.Verdict.MATCH, OwnerStatus.decide(OwnerStatus.OWNER, "1.5.4", 12, listOf(signer), true))
        assertEquals(OwnerStatus.Verdict.MATCH, OwnerStatus.decide(OwnerStatus.BRIDGE, "1.2.1", 4, listOf(signer), false))
    }
    @Test fun olderStillSignedOwnerIsNotCurrent() {
        assertEquals(OwnerStatus.Verdict.WRONG_VERSION, OwnerStatus.decide(OwnerStatus.OWNER, "1.5.1", 9, listOf(signer), true))
        assertEquals(OwnerStatus.Verdict.WRONG_VERSION, OwnerStatus.decide(OwnerStatus.OWNER, "1.5.0", 8, listOf(signer), true))
    }
    @Test fun arbitraryOrMultipleSignerIsDenied() {
        assertEquals(OwnerStatus.Verdict.WRONG_SIGNER, OwnerStatus.decide(OwnerStatus.OWNER, "1.5.4", 12, listOf("a".repeat(64)), true))
        assertEquals(OwnerStatus.Verdict.AMBIGUOUS_SIGNER, OwnerStatus.decide(OwnerStatus.OWNER, "1.5.4", 12, listOf(signer,"a".repeat(64)),true))
        assertEquals(OwnerStatus.Verdict.AMBIGUOUS_SIGNER, OwnerStatus.decide(OwnerStatus.OWNER, "1.5.4", 12, emptyList(),true))
    }
    @Test fun missingOwnerLauncherFailsButBridgeDoesNotNeedOne() {
        assertEquals(OwnerStatus.Verdict.NO_LAUNCHER, OwnerStatus.decide(OwnerStatus.OWNER, "1.5.4", 12, listOf(signer), false))
        assertEquals(OwnerStatus.Verdict.MATCH, OwnerStatus.decide(OwnerStatus.BRIDGE, "1.2.1", 4, listOf(signer), false))
    }
    @Test fun futureVersionDoesNotGetAccidentalAcceptance() {
        assertEquals(OwnerStatus.Verdict.WRONG_VERSION, OwnerStatus.decide(OwnerStatus.OWNER, "9.9", 999, listOf(signer), true))
        val result = OwnerStatus.Finding(OwnerStatus.OWNER, OwnerStatus.Verdict.MATCH).report()
        assertFalse(result.contains("Owner yetkisi verildi"))
    }
}
