package com.example.gptasistan

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** Digests below come from Python json.dumps(sort_keys=True, ensure_ascii=False), not this parser. */
class OwnerGatewayToolTest {
    private val now = 1793700000L
    private val memoryDigest = "7a38de167be01e80d373069ee256f77d31ac55685fa55460938a499246b41f6b"
    private val statusDigest = "e86d32584576beea37a1e0b2ef4c547fa9530c05fbfba59ed7d477a255a8aaa0"
    private fun actor() = JSONObject().put("owner_id", "owner-fixture")
        .put("device_id", "a".repeat(64)).put("owner_key_sha256", "b".repeat(64))
    private fun event(name: String, digest: String, at: Long = now) = JSONObject()
        .put("event", name).put("at", at).put("actor", actor()).put("request_sha256", digest)
    private fun fixture(tool: String = "memory.save", status: String = "awaiting_approval"): JSONObject {
        val memory = tool == "memory.save"
        val digest = if (memory) memoryDigest else statusDigest
        val completed = memory && status == "completed"
        val events = JSONArray().put(event("proposed", digest))
        if (!memory) events.put(event("completed", digest))
        else if (completed) events.put(event("approved", digest, now + 1)).put(event("completed", digest, now + 1))
        else if (status != "awaiting_approval") events.put(event(status, digest, if (status == "expired") now + 300 else now + 1))
        return JSONObject().put("contract", OmegaEnvelope.CONTRACT)
            .put("tool_task_id", (if (memory) "d" else "c").repeat(32))
            .put("tool", tool).put("scope", if (memory) "local.memory" else "local.status")
            .put("arguments", if (memory) JSONObject().put("text", "Türkçe 👑 not") else JSONObject())
            .put("actor", actor()).put("approval_class", if (memory) "owner_approval" else "read_only")
            .put("created_at", now).put("expires_at", now + 300).put("request_sha256", digest)
            .put("status", status).put("approved_at", if (completed) now + 1 else JSONObject.NULL)
            .put("approved_by", if (completed) actor() else JSONObject.NULL)
            .put("result", if (!memory) JSONObject().put("scope", "local-status").put("external_execution", false)
                else if (completed) JSONObject().put("id", 17) else JSONObject.NULL)
            .put("tools_executed", if (!memory || completed) 1 else 0).put("external_actions", 0).put("audit", events)
    }

    @Test fun parsesIndependentlyHashedUnicodeProposalAndKeepsTheReviewedArgumentsImmutable() {
        val raw = fixture()
        val reviewed = OwnerGateway.parseToolTask(raw, "owner-fixture", "https://fixture.example/")
        raw.getJSONObject("arguments").put("text", "Changed after review")
        val body = OwnerGateway.localToolApproval(reviewed, now + 1)
        assertEquals("Türkçe 👑 not", reviewed.memoryText)
        assertEquals("https://fixture.example", reviewed.gatewayBase)
        assertEquals(memoryDigest, reviewed.requestSha256)
        assertEquals(setOf("tool_task_id", "request_sha256", "tool", "arguments", "scope"), body.keys().asSequence().toSet())
        assertEquals("Türkçe 👑 not", body.getJSONObject("arguments").getString("text"))
        assertEquals("memory.save", body.getString("tool"))
        assertEquals("local.memory", body.getString("scope"))
        body.getJSONObject("arguments").put("text", "Changed returned body")
        assertEquals("Türkçe 👑 not", OwnerGateway.localToolApproval(reviewed, now + 1)
            .getJSONObject("arguments").getString("text"))
        assertThrows(UnsupportedOperationException::class.java) {
            (reviewed.audit as MutableList<OwnerGateway.ToolAudit>).clear()
        }
    }

    @Test fun acceptsOnlyMatchingApprovedExecutionAndItsAuditEvidence() {
        val task = OwnerGateway.parseToolTask(fixture(status = "completed"))
        assertEquals(17L, task.memoryId)
        assertEquals(task.actor, task.approvedBy)
        assertEquals(now + 1, task.approvedAt)
        assertEquals(1L, task.toolsExecuted)
        assertEquals(listOf("proposed", "approved", "completed"), task.audit.map { it.event })
        val local = OwnerGateway.parseToolTask(fixture("status", "completed"))
        assertEquals("read_only", local.approvalClass)
        assertNull(local.memoryText)
        assertNull(local.approvedBy)
    }

    @Test fun rejectsUnknownCapabilitiesPolicyScopeActorDigestAndUnexpectedFields() {
        val invalid = listOf(
            fixture().put("tool", "shell"), fixture().put("scope", "remote.admin"),
            fixture().put("approval_class", "read_only"), fixture().put("request_sha256", "0".repeat(64)),
            fixture().put("handler", "memory.save"), fixture().put("external_actions", 1),
            fixture().put("tools_executed", 1), fixture().put("status", "executed_shell"),
            fixture().put("expires_at", now + 301),
            fixture().also { it.getJSONObject("actor").put("device_id", "not-a-fingerprint") },
            fixture().also { it.getJSONObject("arguments").put("extra", true) },
            fixture().also { it.getJSONArray("audit").getJSONObject(0).put("private_text", "not allowed") },
            fixture(status = "completed").put("approved_by", actor().put("owner_id", "other-owner")),
            fixture(status = "completed").put("result", JSONObject().put("id", 0)),
        )
        invalid.forEach { value ->
            assertThrows(IllegalArgumentException::class.java) { OwnerGateway.parseToolTask(value) }
        }
        assertThrows(IllegalArgumentException::class.java) { OwnerGateway.parseToolTask(fixture(), "other-owner") }
    }

    @Test fun expirationCancellationAndReadOnlyStatusCannotBeApproved() {
        val pending = OwnerGateway.parseToolTask(fixture())
        assertThrows(IllegalArgumentException::class.java) { OwnerGateway.localToolApproval(pending, now + 300) }
        assertThrows(IllegalArgumentException::class.java) { OwnerGateway.localToolApproval(pending, now - 31) }
        for (task in listOf(OwnerGateway.parseToolTask(fixture(status = "cancelled")),
            OwnerGateway.parseToolTask(fixture(status = "expired")),
            OwnerGateway.parseToolTask(fixture("status", "completed")))) {
            assertThrows(IllegalArgumentException::class.java) { OwnerGateway.localToolApproval(task, now + 1) }
        }
    }

    @Test fun approvalAllowsOnlyTheExistingThirtySecondAuthenticationClockSkew() {
        val pending = OwnerGateway.parseToolTask(fixture())
        val atLowerBoundary = OwnerGateway.localToolApproval(pending, now - 30)
        assertEquals(memoryDigest, atLowerBoundary.getString("request_sha256"))
        assertEquals("Türkçe 👑 not", atLowerBoundary.getJSONObject("arguments").getString("text"))
        assertThrows(IllegalArgumentException::class.java) { OwnerGateway.localToolApproval(pending, now - 31) }
        assertThrows(IllegalArgumentException::class.java) { OwnerGateway.localToolApproval(pending, -1) }
        assertEquals(memoryDigest, OwnerGateway.localToolApproval(pending, now + 299).getString("request_sha256"))
        assertThrows(IllegalArgumentException::class.java) { OwnerGateway.localToolApproval(pending, now + 300) }
    }

    @Test fun proposalAndReferenceBodiesKeepOnlyTheApprovedSchema() {
        val body = OwnerGateway.localMemoryProposal("Local note")
        assertEquals(setOf("tool", "arguments", "scope"), body.keys().asSequence().toSet())
        assertEquals("Local note", body.getJSONObject("arguments").getString("text"))
        for (text in listOf("", " ", "x".repeat(8001))) {
            assertThrows(IllegalArgumentException::class.java) { OwnerGateway.localMemoryProposal(text) }
        }
        val reference = OwnerGateway.localToolReference(OwnerGateway.parseToolTask(fixture()))
        assertEquals(setOf("tool_task_id", "request_sha256"), reference.keys().asSequence().toSet())
        assertEquals(memoryDigest, reference.getString("request_sha256"))
    }

    @Test fun allLocalToolRoutesUseTheExistingOwnerDeviceCanonicalEnvelope() {
        val body = OwnerGateway.localMemoryProposal("Local note").toString().toByteArray(Charsets.UTF_8)
        for (path in listOf(OmegaEnvelope.TOOL_TASKS, OmegaEnvelope.TOOL_STATUS,
            OmegaEnvelope.TOOL_APPROVE, OmegaEnvelope.TOOL_CANCEL)) {
            val canonical = OmegaEnvelope.canonical(path, body, now.toString(), "e".repeat(32),
                "owner-fixture", "a".repeat(64)).toString(Charsets.UTF_8)
            assertTrue(canonical.contains("\n$path\n"))
            assertTrue(canonical.endsWith("\nowner-fixture\n" + "a".repeat(64)))
        }
    }
}
