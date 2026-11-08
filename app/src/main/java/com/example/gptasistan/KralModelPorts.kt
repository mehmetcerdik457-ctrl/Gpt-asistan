package com.example.gptasistan

import android.content.Context

/**
 * Boundary for model transports; no automatic network request or local inference
 * happens when a port is instantiated. Never persist provider API keys here.
 */
internal interface KralModelPort {
    fun verifiedModels(): List<OwnerGateway.Model>
    fun reply(context: Context, modelId: String, message: String): OwnerGateway.Reply
}

/**
 * Delegates only to the already-enrolled dual-signed Owner Gateway. Remote
 * model selection must still be fresh, verified and bound to the same owner.
 */
internal class SignedOwnerModelPort(
    private val base: String,
    private val ownerId: String,
) : KralModelPort {
    init {
        require(OwnerGateway.validBase(base)) { "OWNER_SERVER_HTTPS_REQUIRED" }
        require(ownerId.isNotBlank()) { "OWNER_ID_REQUIRED" }
    }

    override fun verifiedModels(): List<OwnerGateway.Model> =
        OwnerGateway.verifiedModels(base, ownerId)

    override fun reply(
        context: Context,
        modelId: String,
        message: String,
    ): OwnerGateway.Reply {
        require(message.isNotBlank()) { "EMPTY_MESSAGE" }

        // The owner bound to this port must match the enrolled device state.
        val localOwner = context.getSharedPreferences("kral_model", Context.MODE_PRIVATE)
            .getString("owner_id", "").orEmpty()
        if (localOwner != ownerId) throw SecurityException("OWNER_MISMATCH")
        if (verifiedModels().none { it.id == modelId }) {
            throw SecurityException("MODEL_NOT_VERIFIED")
        }
        return OwnerGateway.replyWithMetadata(context, base, modelId, message)
    }
}

/**
 * Reserved on-device inference boundary. No local engine is currently shipped.
 * An HTTPS server on the LAN is not silently treated as an on-device model.
 */
internal object UnavailableLocalModelPort : KralModelPort {
    override fun verifiedModels(): List<OwnerGateway.Model> = emptyList()

    override fun reply(
        context: Context,
        modelId: String,
        message: String,
    ): OwnerGateway.Reply = throw SecurityException("LOCAL_RUNTIME_NOT_CONFIGURED")
}
