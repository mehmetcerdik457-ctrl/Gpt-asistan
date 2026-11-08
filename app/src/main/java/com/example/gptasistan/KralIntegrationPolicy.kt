package com.example.gptasistan

/**
 * Permission decision for user-visible integration controls.
 *
 * This is intentionally not an authorization token for a remote service:
 * the existing OwnerGateway still performs P-256 request signing and remote
 * owner verification for every network request.
 */
internal enum class KralIntegrationAction {
    INSPECT_CIHAT,
    OPEN_CIHAT,
    READ_OWNER_BRIDGE,
    READ_OWNER_WORKER_STATUS,
    PRIVILEGED_EXTERNAL_WRITE,
}

internal data class KralIntegrationContext(
    val ownerUnlocked: Boolean,
    val encryptedStoreReady: Boolean,
    val busy: Boolean,
    val cihatIdentityVerified: Boolean = false,
    val ownerServerConfigured: Boolean = false,
)

internal enum class KralIntegrationDecision {
    ALLOW_LOCAL_READ,
    ALLOW_CONFIRMED_CIHAT_HANDOFF,
    ALLOW_SIGNED_READ_ATTEMPT,
    DENY_OWNER_LOCKED,
    DENY_STORAGE_UNAVAILABLE,
    DENY_BUSY,
    DENY_CIHAT_UNVERIFIED,
    DENY_OWNER_SERVER_UNCONFIGURED,
    DENY_PRIVILEGED_ACTION,
}

internal object KralIntegrationPolicy {
    fun decide(
        action: KralIntegrationAction,
        context: KralIntegrationContext,
    ): KralIntegrationDecision {
        if (!context.ownerUnlocked) return KralIntegrationDecision.DENY_OWNER_LOCKED
        if (!context.encryptedStoreReady) return KralIntegrationDecision.DENY_STORAGE_UNAVAILABLE
        if (context.busy) return KralIntegrationDecision.DENY_BUSY

        return when (action) {
            KralIntegrationAction.INSPECT_CIHAT,
            KralIntegrationAction.READ_OWNER_BRIDGE ->
                KralIntegrationDecision.ALLOW_LOCAL_READ

            KralIntegrationAction.OPEN_CIHAT ->
                if (context.cihatIdentityVerified)
                    KralIntegrationDecision.ALLOW_CONFIRMED_CIHAT_HANDOFF
                else KralIntegrationDecision.DENY_CIHAT_UNVERIFIED

            KralIntegrationAction.READ_OWNER_WORKER_STATUS ->
                if (context.ownerServerConfigured)
                    KralIntegrationDecision.ALLOW_SIGNED_READ_ATTEMPT
                else KralIntegrationDecision.DENY_OWNER_SERVER_UNCONFIGURED

            KralIntegrationAction.PRIVILEGED_EXTERNAL_WRITE ->
                KralIntegrationDecision.DENY_PRIVILEGED_ACTION
        }
    }
}
