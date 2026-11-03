package com.example.gptasistan

/**
 * Default-deny operation policy between the natural-language parser and effectful tools.
 * No authority is inferred from prompts, documents or model output.
 * This module cannot unlock a device, enroll a key or authorize external writes.
 */
internal data class OwnerExecutionContext(
    val ownerUnlocked: Boolean,
    val encryptedStoreReady: Boolean,
    val verifiedRemoteModel: Boolean = false,
)

internal enum class OwnerExecutionDecision {
    ALLOW_LOCAL_ROUTINE,
    ALLOW_SIGNED_REMOTE_ATTEMPT,
    DENY_OWNER_LOCKED,
    DENY_STORAGE_UNAVAILABLE,
    DENY_REMOTE_NOT_VERIFIED,
    DENY_UNSUPPORTED,
}

internal object OwnerExecutionPolicy {
    fun decide(command: KralCommand, context: OwnerExecutionContext): OwnerExecutionDecision {
        if (!context.ownerUnlocked) return OwnerExecutionDecision.DENY_OWNER_LOCKED
        if (!context.encryptedStoreReady) return OwnerExecutionDecision.DENY_STORAGE_UNAVAILABLE
        return when (command) {
            is KralCommand.Save,
            KralCommand.ListMemory,
            is KralCommand.Recall,
            is KralCommand.AddTask,
            KralCommand.ListTasks,
            is KralCommand.FinishTask,
            is KralCommand.Speak,
            KralCommand.Help,
            KralCommand.Invalid -> OwnerExecutionDecision.ALLOW_LOCAL_ROUTINE
            is KralCommand.Chat -> if (context.verifiedRemoteModel)
                OwnerExecutionDecision.ALLOW_SIGNED_REMOTE_ATTEMPT
                else OwnerExecutionDecision.DENY_REMOTE_NOT_VERIFIED
            else -> OwnerExecutionDecision.DENY_UNSUPPORTED
        }
    }

    // Privileged external actions still require a separate, scoped owner approval capability.
    fun allowPrivilegedExternalAction(): Boolean = false
}
