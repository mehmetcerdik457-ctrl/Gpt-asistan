package com.example.gptasistan

import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/**
 * One explicitly prepared logical task. Keep this in memory for an owner-approved
 * manual retry; preparing again creates a different task and can incur a new charge.
 * No credential, mutable JSON object, or automatic retry is retained here.
 */
class TaskSubmission private constructor(
    val base: String,
    val owner: String,
    val model: String,
    val expert: String,
    val input: String,
    val requiresApproval: Boolean,
    val requestId: String,
    private val wireBody: String,
) {
    val requestSha256: String = OwnerGateway.taskRequestDigest(model, expert, input)

    /** Configuration changes require the owner to prepare a new logical task. */
    fun matches(base: String, owner: String, model: String): Boolean =
        OwnerGateway.validBase(base) && this.base == base.trimEnd('/') &&
            this.owner == owner && this.model == model

    internal fun requestBytes(): ByteArray = wireBody.toByteArray(Charsets.UTF_8)

    // A retained ViewModel may be inspected or logged; do not print the task text.
    override fun toString(): String = "TaskSubmission(requestId=$requestId)"

    companion object {
        internal fun create(
            base: String, owner: String, model: String, expert: String,
            input: String, requiresApproval: Boolean = false,
        ): TaskSubmission {
            require(OwnerGateway.validBase(base) && OmegaEnvelope.validOwner(owner))
            require(model.isNotBlank() && model.length <= 200 && !model.any { it.isISOControl() })
            require(expert in OwnerGateway.EXPERTS)
            require(input.isNotBlank() && input.length <= 8000 && wellFormedUnicode(input))
            val requestId = UUID.randomUUID().toString().replace("-", "")
            val body = JSONObject().put("input", input).put("model", model)
                .put("expert", expert).put("tools", JSONArray())
                .put("requires_approval", requiresApproval)
                .put("client_request_id", requestId).put("idempotency_key", requestId)
                .toString()
            return TaskSubmission(base.trimEnd('/'), owner, model, expert, input,
                requiresApproval, requestId, body)
        }

        private fun wellFormedUnicode(value: String): Boolean {
            var index = 0
            while (index < value.length) {
                val char = value[index++]
                if (char.isHighSurrogate()) {
                    if (index >= value.length || !value[index++].isLowSurrogate()) return false
                } else if (char.isLowSurrogate()) return false
            }
            return true
        }
    }
}
