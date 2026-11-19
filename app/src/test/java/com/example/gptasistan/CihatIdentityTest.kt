package com.example.gptasistan

import org.junit.Assert.*
import org.junit.Test

/** No Android runtime; evaluates identity policy only. */
class CihatIdentityTest {
    @Test fun exactPreserved321VersionAndSignerRequired() {
        assertEquals(CihatIdentity.State.VERIFIED_321,
            CihatIdentity.decide(893L, listOf(CihatIdentity.FORENSIC_SIGNER_SHA256), true))
        assertEquals(CihatIdentity.State.VERIFIED_321,
            CihatIdentity.decide(893L, listOf(CihatIdentity.FORENSIC_SIGNER_SHA256.uppercase()), true))
    }

    @Test fun mismatchedVersionNeverEnablesHandoff() {
        for (version in listOf(0L, 892L, 894L, 999L)) {
            assertEquals(CihatIdentity.State.VERSION_MISMATCH,
                CihatIdentity.decide(version, listOf(CihatIdentity.FORENSIC_SIGNER_SHA256), true))
        }
    }

    @Test fun certificateMismatchAndAdditionalSignerFailClosed() {
        val expected = CihatIdentity.FORENSIC_SIGNER_SHA256
        val other = "b".repeat(64)
        for (signers in listOf(emptyList(), listOf(other), listOf(expected, other))) {
            assertEquals(CihatIdentity.State.SIGNER_MISMATCH,
                CihatIdentity.decide(893L, signers, true))
        }
    }

    @Test fun realLaunchableComponentIsRequired() {
        assertEquals(CihatIdentity.State.NOT_LAUNCHABLE,
            CihatIdentity.decide(893L, listOf(CihatIdentity.FORENSIC_SIGNER_SHA256), false))
    }

    @Test fun reportNeverClaimsModelOrOwnerAuthorization() {
        val verified = CihatIdentity.Result(CihatIdentity.State.VERIFIED_321,
            893L, CihatIdentity.FORENSIC_SIGNER_SHA256)
        assertTrue(verified.verified)
        assertTrue(verified.report().contains("yetkisi"))
        assertTrue(verified.report().contains("model"))
        assertFalse(CihatIdentity.Result(CihatIdentity.State.NOT_INSTALLED).verified)
        assertTrue(CihatIdentity.Result(CihatIdentity.State.NOT_INSTALLED).report().contains("Eşleşme yok"))
    }
}
