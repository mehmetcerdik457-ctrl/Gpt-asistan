package com.example.gptasistan

import org.junit.Assert.assertEquals
import org.junit.Test

class KralIntegrationPolicyTest {
    private fun checked(
        action: KralIntegrationAction,
        context: KralIntegrationContext,
    ) = KralIntegrationPolicy.decide(action, context)

    private val valid = KralIntegrationContext(
        ownerUnlocked = true,
        encryptedStoreReady = true,
        busy = false,
        cihatIdentityVerified = true,
        ownerServerConfigured = true,
    )

    @Test fun ownerLockedBlocksAllIntegrationActions() {
        val ctx = valid.copy(ownerUnlocked = false)
        KralIntegrationAction.values().forEach { action ->
            assertEquals(KralIntegrationDecision.DENY_OWNER_LOCKED, checked(action, ctx))
        }
    }

    @Test fun unavailableEncryptedStoreBlocksAllIntegrationActions() {
        val ctx = valid.copy(encryptedStoreReady = false)
        KralIntegrationAction.values().forEach { action ->
            assertEquals(KralIntegrationDecision.DENY_STORAGE_UNAVAILABLE, checked(action, ctx))
        }
    }

    @Test fun busySessionBlocksAllIntegrationActions() {
        val ctx = valid.copy(busy = true)
        KralIntegrationAction.values().forEach { action ->
            assertEquals(KralIntegrationDecision.DENY_BUSY, checked(action, ctx))
        }
    }

    @Test fun statusReadsDoNotRequireThirdPartyPackages() {
        val ctx = valid.copy(cihatIdentityVerified = false, ownerServerConfigured = false)
        assertEquals(
            KralIntegrationDecision.ALLOW_LOCAL_READ,
            checked(KralIntegrationAction.INSPECT_CIHAT, ctx)
        )
        assertEquals(
            KralIntegrationDecision.ALLOW_LOCAL_READ,
            checked(KralIntegrationAction.READ_OWNER_BRIDGE, ctx)
        )
    }

    @Test fun thirdPartyHandoffRequiresVerifiedPackageIdentity() {
        assertEquals(
            KralIntegrationDecision.DENY_CIHAT_UNVERIFIED,
            checked(KralIntegrationAction.OPEN_CIHAT, valid.copy(cihatIdentityVerified = false))
        )
        assertEquals(
            KralIntegrationDecision.ALLOW_CONFIRMED_CIHAT_HANDOFF,
            checked(KralIntegrationAction.OPEN_CIHAT, valid)
        )
    }

    @Test fun workerStatusRequiresConfiguredOwnerServer() {
        assertEquals(
            KralIntegrationDecision.DENY_OWNER_SERVER_UNCONFIGURED,
            checked(KralIntegrationAction.READ_OWNER_WORKER_STATUS,
                valid.copy(ownerServerConfigured = false))
        )
        assertEquals(
            KralIntegrationDecision.ALLOW_SIGNED_READ_ATTEMPT,
            checked(KralIntegrationAction.READ_OWNER_WORKER_STATUS, valid)
        )
    }

    @Test fun privilegedExternalWriteNeverAuthorizedByUiPolicy() {
        assertEquals(
            KralIntegrationDecision.DENY_PRIVILEGED_ACTION,
            checked(KralIntegrationAction.PRIVILEGED_EXTERNAL_WRITE, valid)
        )
    }
}
