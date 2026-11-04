package com.example.gptasistan

import android.content.Context
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/** No live HTTP, model, or owner Keystore calls; exercise the real request/parser gates. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class TaskSubmissionTest {
    private val base = "https://owner.example"
    private val owner = "OwnerFixture"
    private val model = "verified-model"

    private fun submission(input: String = "İncele \"KRAL\"\n😀", approval: Boolean = false) =
        TaskSubmission.create(base, owner, model, "test-engineer", input, approval)

    @Test fun manualReplayUsesFrozenExactBytesAndOneLogicalKey() {
        val request = submission()
        val first = request.requestBytes()
        val payload = JSONObject(first.toString(Charsets.UTF_8))
        assertTrue(request.requestId.matches(Regex("[a-f0-9]{32}")))
        assertEquals(request.requestId, payload.getString("idempotency_key"))
        assertEquals(request.requestId, payload.getString("client_request_id"))
        assertEquals(request.input, payload.getString("input"))
        assertEquals(model, payload.getString("model"))
        assertEquals("test-engineer", payload.getString("expert"))
        assertFalse(payload.getBoolean("requires_approval"))
        assertEquals(0, payload.getJSONArray("tools").length())
        payload.put("input", "mutated JSON copy")
        first.fill(0)
        val replay = request.requestBytes()
        assertEquals(request.input, JSONObject(replay.toString(Charsets.UTF_8)).getString("input"))
        assertArrayEquals(replay, request.requestBytes())
        assertEquals(OwnerGateway.taskRequestDigest(model, "test-engineer", request.input), request.requestSha256)
    }

    @Test fun newLogicalSubmissionDoesNotDeduplicateIdenticalTextOrChangedApproval() {
        val first = submission()
        val next = submission()
        val approved = submission(approval = true)
        assertNotEquals(first.requestId, next.requestId)
        assertNotEquals(first.requestId, approved.requestId)
        assertEquals(first.requestSha256, next.requestSha256)
        assertTrue(JSONObject(approved.requestBytes().toString(Charsets.UTF_8)).getBoolean("requires_approval"))
    }

    @Test fun scopeOnlyNormalizesThePermittedRootSlash() {
        val request = submission()
        assertTrue(request.matches(base, owner, model))
        assertTrue(request.matches("$base/", owner, model))
        assertFalse(request.matches("https://other.example", owner, model))
        assertFalse(request.matches(base, "OtherOwner", model))
        assertFalse(request.matches(base, owner, "other-model"))
        assertFalse(request.matches("$base////", owner, model))
        assertFalse(request.matches("$base/?token=private", owner, model))
    }

    @Test fun preparationRejectsUnboundedMalformedAndUnapprovedInputs() {
        for (input in listOf("", "  ", "a".repeat(8001), "broken\uD83D", "\uDE00broken")) {
            assertThrows(IllegalArgumentException::class.java) { submission(input) }
        }
        assertEquals(8000, submission("a".repeat(7998) + "😀").input.length)
        assertThrows(IllegalArgumentException::class.java) {
            TaskSubmission.create(base, owner, model, "execute-shell", "test")
        }
        assertThrows(IllegalArgumentException::class.java) {
            TaskSubmission.create("http://owner.example", owner, model, "test-engineer", "test")
        }
        assertThrows(IllegalArgumentException::class.java) {
            TaskSubmission.create(base, "owner\nsecond", model, "test-engineer", "test")
        }
        assertThrows(IllegalArgumentException::class.java) {
            TaskSubmission.create(base, owner, "model\rsecond", "test-engineer", "test")
        }
    }

    @Test fun loggingTheRetainedObjectDoesNotRevealItsTextOrConfiguration() {
        val request = submission("Private synthetic task input")
        assertEquals("TaskSubmission(requestId=${request.requestId})", request.toString())
        assertFalse(request.toString().contains(request.input))
        assertFalse(request.toString().contains(base))
        assertFalse(request.toString().contains(owner))
    }

    private fun response(request: TaskSubmission) = JSONObject()
        .put("contract", OmegaEnvelope.CONTRACT).put("task_id", request.requestId)
        .put("client_request_id", request.requestId).put("status", "queued")
        .put("request_sha256", request.requestSha256).put("retryable", false)
        .put("tools_executed", 0).put("external_actions", 0)

    @Test fun acceptanceIsBoundToLogicalKeyAndExactTaskDigest() {
        val request = submission()
        val accepted = OwnerGateway.parseTaskForSubmission(response(request), request)
        assertEquals(request.requestId, accepted.taskId)
        assertEquals("queued", accepted.status)
        val unrelated = submission()
        assertThrows(IllegalArgumentException::class.java) {
            OwnerGateway.parseTaskForSubmission(response(unrelated), request)
        }
        assertThrows(IllegalArgumentException::class.java) {
            OwnerGateway.parseTaskForSubmission(response(request).put("request_sha256", "0".repeat(64)), request)
        }
        assertThrows(IllegalArgumentException::class.java) {
            OwnerGateway.parseTaskForSubmission(response(request).put("client_request_id", JSONObject.NULL), request)
        }
        assertThrows(IllegalArgumentException::class.java) {
            OwnerGateway.parseTaskForSubmission(response(request).put("client_request_id", "b".repeat(32)), request)
        }
    }

    @Test fun changedConfigurationIsRejectedBeforeNetworkOrKeystoreSigning() {
        val request = submission()
        val context = RuntimeEnvironment.getApplication()
        val prefs = context.getSharedPreferences("kral_model", Context.MODE_PRIVATE)
        val valid = mapOf("endpoint" to base, "owner_id" to owner, "model" to model)
        try {
            for ((field, replacement) in mapOf("endpoint" to "https://other.example", "owner_id" to "OtherOwner", "model" to "other-model")) {
                prefs.edit().clear().apply {
                    valid.forEach { (key, value) -> putString(key, value) }
                    putString(field, replacement)
                }.commit()
                val error = assertThrows(SecurityException::class.java) {
                    OwnerGateway.submitTask(context, base, request)
                }
                assertEquals("TASK_SUBMISSION_SCOPE_CHANGED", error.message)
            }
            prefs.edit().clear().apply { valid.forEach { (key, value) -> putString(key, value) } }.commit()
            assertEquals("TASK_SUBMISSION_SCOPE_CHANGED", assertThrows(SecurityException::class.java) {
                OwnerGateway.submitTask(context, "https://different.example", request)
            }.message)
        } finally {
            prefs.edit().clear().commit()
        }
    }

    @Test fun aNewSubmissionRequiresFreshModelVerificationBeforeAnyPost() {
        OwnerGateway.clear()
        assertEquals("MODEL_NOT_VERIFIED", assertThrows(SecurityException::class.java) {
            OwnerGateway.prepareTaskSubmission(base, owner, model, "test-engineer", "task")
        }.message)
    }
}
