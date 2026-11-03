package com.example.gptasistan

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

/** Wire/parser tests only. Fixtures are not live provider or Keystore evidence. */
class OwnerGatewayTest {
    private val now = 1792537200L
    private fun modelJson() = JSONObject().put("contract", OmegaEnvelope.CONTRACT)
        .put("models", org.json.JSONArray().put(JSONObject().put("id", "returned-model")
            .put("provider", "openai").put("verified_at", now).put("latency_ms", 23)))

    @Test fun rejectsCredentialsQueriesAndNonRootUrlsBeforeSigning() {
        assertTrue(OwnerGateway.validBase("https://server.example"))
        assertTrue(OwnerGateway.validBase("https://server.example:8443/"))
        listOf("http://server.example", "https://secret@server.example", "https://server.example/?token=secret",
            "https://server.example/api/chat", "https://server.example/#fragment", "https://server.example:0").forEach {
            assertFalse(it, OwnerGateway.validBase(it))
        }
    }

    @Test fun registryRequiresFreshTypedVerificationAndUniqueProviderReturnedIds() {
        assertEquals("returned-model", OwnerGateway.parseModels(modelJson(), now).single().id)
        for (field in listOf("verified_at", "latency_ms")) {
            val value = modelJson()
            value.getJSONArray("models").getJSONObject(0).put(field, "123")
            assertThrows(IllegalArgumentException::class.java) { OwnerGateway.parseModels(value, now) }
        }
        val stale = modelJson()
        stale.getJSONArray("models").getJSONObject(0).put("verified_at", now - 301)
        assertThrows(IllegalArgumentException::class.java) { OwnerGateway.parseModels(stale, now) }
        val duplicate = modelJson()
        duplicate.getJSONArray("models").put(duplicate.getJSONArray("models").getJSONObject(0))
        assertThrows(IllegalArgumentException::class.java) { OwnerGateway.parseModels(duplicate, now) }
        val wrongContract = modelJson().put("contract", "private-omega")
        assertThrows(IllegalArgumentException::class.java) { OwnerGateway.parseModels(wrongContract, now) }
    }

    @Test fun replyMustReportSelectedProviderAndModelWithNonemptyText() {
        val model = OwnerGateway.Model("returned-model", "openai", now, 23)
        fun response() = JSONObject().put("contract", OmegaEnvelope.CONTRACT).put("model", model.id)
            .put("provider", model.provider).put("latency_ms", 50).put("text", "Merhaba Mehmet")
        assertEquals("Merhaba Mehmet", OwnerGateway.parseReply(response(), model))
        listOf(response().put("model", "requested-alias"), response().put("provider", "different-provider"),
            response().put("text", " "), response().put("text", 42), response().put("latency_ms", -1)).forEach {
            assertThrows(IllegalArgumentException::class.java) { OwnerGateway.parseReply(it, model) }
        }
    }

    @Test fun canonicalBindsExactBytesPathOwnerDeviceAndTimestamp() {
        val body = "{}".toByteArray()
        val device = "a".repeat(64)
        val nonce = "b".repeat(48)
        val canonical = OmegaEnvelope.canonical(OmegaEnvelope.CHAT, body, "1792537200", nonce, "Mehmet", device)
        assertEquals("OMEGA-OWNER-API-V1\nPOST\n/api/v1/owner/chat\n" +
            "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a\n" +
            "1792537200\n$nonce\nMehmet\n$device", canonical.toString(Charsets.UTF_8))
        assertFalse(canonical.contentEquals(OmegaEnvelope.canonical(OmegaEnvelope.MODELS, body, "1792537200", nonce, "Mehmet", device)))
        assertFalse(canonical.contentEquals(OmegaEnvelope.canonical(OmegaEnvelope.CHAT, "{ }".toByteArray(), "1792537200", nonce, "Mehmet", device)))
        assertThrows(IllegalArgumentException::class.java) {
            OmegaEnvelope.canonical("/api/v1/owner/delete", body, "1792537200", nonce, "Mehmet", device)
        }
        assertThrows(IllegalArgumentException::class.java) {
            OmegaEnvelope.canonical(OmegaEnvelope.CHAT, body, "1792537200", nonce, "Mehmet\nOther", device)
        }
    }

    private fun taskJson(status: String = "completed", resultText: String? = "Uzman incelemesi tamamlandı") =
        JSONObject().put("contract", OmegaEnvelope.CONTRACT)
            .put("task_id", "a".repeat(32)).put("status", status)
            .put("request_sha256", "b".repeat(64))
            .put("result", resultText ?: JSONObject.NULL)
            .put("result_sha256", resultText?.let { KralAndroidCore.sha256Hex(it) } ?: JSONObject.NULL)
            .put("response_id", "resp_synthetic_123")
            .put("provider_request_id", "req_synthetic_123")
            .put("provider_http_status", 200)
            .put("provider_error_code", JSONObject.NULL)
            .put("retryable", false).put("retry_after_seconds", JSONObject.NULL)
            .put("error", JSONObject.NULL).put("tools_executed", 0).put("external_actions", 0)

    @Test fun taskResponseParserChecksLifecycleHashesAndNoToolExecution() {
        val completed = OwnerGateway.parseTask(taskJson())
        assertEquals("a".repeat(32), completed.taskId)
        assertEquals("completed", completed.status)
        assertEquals("Uzman incelemesi tamamlandı", completed.result)
        assertEquals("resp_synthetic_123", completed.responseId)
        assertEquals("req_synthetic_123", completed.providerRequestId)
        assertEquals(200, completed.providerHttpStatus)
        assertFalse(completed.retryable)

        val queued = OwnerGateway.parseTask(taskJson("queued", null))
        assertEquals("queued", queued.status)
        assertNull(queued.result)
        assertNull(queued.resultSha256)
    }

    @Test fun taskResponseRejectsForgedIdsHashesStatusesAndToolCounts() {
        val invalid = listOf(
            taskJson().put("task_id", "not-a-task-id"),
            taskJson().put("request_sha256", "short"),
            taskJson().put("status", "executed_shell"),
            taskJson().put("result_sha256", "0".repeat(64)),
            taskJson().put("tools_executed", 1),
            taskJson().put("external_actions", 1),
            taskJson().put("retryable", "true"),
            taskJson().put("provider_http_status", 700),
            taskJson().put("response_id", "bad response id"),
        )
        invalid.forEach { payload ->
            assertThrows(IllegalArgumentException::class.java) { OwnerGateway.parseTask(payload) }
        }
    }

    @Test fun taskRoutesAreBoundToExistingDualP256Envelope() {
        val body = JSONObject().put("task_id", "a".repeat(32)).toString().toByteArray()
        val nonce = "b".repeat(48)
        val device = "c".repeat(64)
        for (path in listOf(OmegaEnvelope.TASKS, OmegaEnvelope.TASK_STATUS,
            OmegaEnvelope.TASK_CANCEL, OmegaEnvelope.TASK_APPROVE)) {
            val canonical = OmegaEnvelope.canonical(path, body, "1792537200", nonce, "Mehmet", device)
            assertTrue(canonical.toString(Charsets.UTF_8).contains(path))
        }
    }

    @Test fun workerPathUsesExistingDualP256CanonicalButOtherPathsDenied() {
        val body = "{\"tasks\":[{\"id\":\"W01\",\"kind\":\"status\",\"args\":{}}],\"max_parallel\":1}".toByteArray()
        val nonce = "b".repeat(48)
        val device = "a".repeat(64)
        val signed = OmegaEnvelope.canonical(OmegaEnvelope.WORKERS, body, "1792537200",
            nonce, "Mehmet", device).toString(Charsets.UTF_8)
        assertTrue(signed.contains("/api/v1/owner/workers"))
        assertFalse(signed.contains("/api/v1/owner/chat"))
        assertThrows(IllegalArgumentException::class.java) {
            OmegaEnvelope.canonical("/api/v1/owner/github-merge", body, "1792537200", nonce, "Mehmet", device)
        }
    }

    private fun workerTasks() = org.json.JSONArray().put(JSONObject()
        .put("id", "W01").put("kind", "status").put("args", JSONObject()))

    private fun safeWorkers(tasks: org.json.JSONArray = workerTasks(), parallel: Int = 1) = JSONObject()
        .put("contract", OmegaEnvelope.CONTRACT)
        .put("mode", "SIGNED_OWNER_READ_ONLY_LOCAL")
        .put("task_sha256", OwnerGateway.workerTaskDigest(tasks))
        .put("logical_worker_slots", 50).put("executed_tasks", tasks.length())
        .put("parallel_limit", parallel).put("provider_calls", 0)
        .put("external_actions", 0).put("automatic_approvals", 0)
        .put("results", org.json.JSONArray().put(JSONObject()
            .put("id", "W01").put("status", "COMPLETED_LOCAL_READ")
            .put("result", JSONObject().put("scope", "local-owner-reads"))))

    @Test fun workerCanonicalShaMatchesPythonSortKeysUtf8Contract() {
        assertEquals("c9c33602cded68f89b200a4489094eb94cdfa8712e5a73d7e2447edffd2fbe72",
            OwnerGateway.workerTaskDigest(workerTasks()))
        val unicode = org.json.JSONArray()
            .put(JSONObject().put("id", "W01").put("kind", "memory.search")
                .put("args", JSONObject().put("query", "İstanbul cuma").put("limit", 5)))
            .put(JSONObject().put("id", "W02").put("kind", "history.recent")
                .put("args", JSONObject().put("limit", 2)))
        assertEquals("0cd44897334226832ac06b973e118368db60d03486199bc3a36b42a711b5404d",
            OwnerGateway.workerTaskDigest(unicode))
    }

    @Test fun localWorkersRejectForgedExternalActionsAndModelCalls() {
        val tasks = workerTasks()
        assertEquals(1, OwnerGateway.parseLocalWorkers(safeWorkers(tasks), tasks, 1).length())
        listOf(
            safeWorkers().put("provider_calls", 1),
            safeWorkers().put("external_actions", 1),
            safeWorkers().put("automatic_approvals", 1),
            safeWorkers().put("mode", "REMOTE_AUTONOMOUS"),
            safeWorkers().put("task_sha256", "a".repeat(64)),
            safeWorkers().put("executed_tasks", 50),
            safeWorkers().put("parallel_limit", 4),
            safeWorkers().put("parallel_limit", "1")
        ).forEach { forged ->
            assertThrows(IllegalArgumentException::class.java) {
                OwnerGateway.parseLocalWorkers(forged, tasks, 1)
            }
        }
        assertThrows(IllegalArgumentException::class.java) {
            OwnerGateway.parseLocalWorkers(safeWorkers().put("results", org.json.JSONArray()
                .put(JSONObject().put("id", "W01").put("status", "EXECUTED_SHELL"))), tasks, 1)
        }
    }

    @Test fun localWorkersRequireExactlyTheRequestedJobIdsInOrder() {
        val tasks = org.json.JSONArray().put(JSONObject()
            .put("id", "W01").put("kind", "status").put("args", JSONObject()))
            .put(JSONObject().put("id", "W02").put("kind", "models.cached").put("args", JSONObject()))
        fun response() = safeWorkers(tasks).put("executed_tasks", 2)
            .put("results", org.json.JSONArray()
                .put(JSONObject().put("id", "W01").put("status", "COMPLETED_LOCAL_READ"))
                .put(JSONObject().put("id", "W02").put("status", "BLOCKED_LOCAL_READ")))
        assertEquals(2, OwnerGateway.parseLocalWorkers(response(), tasks, 1).length())

        listOf(
            org.json.JSONArray().put(JSONObject().put("id", "W02").put("status", "COMPLETED_LOCAL_READ"))
                .put(JSONObject().put("id", "W01").put("status", "BLOCKED_LOCAL_READ")),
            org.json.JSONArray().put(JSONObject().put("id", "W01").put("status", "COMPLETED_LOCAL_READ"))
                .put(JSONObject().put("id", "W01").put("status", "BLOCKED_LOCAL_READ")),
            org.json.JSONArray().put(JSONObject().put("id", "W01").put("status", "COMPLETED_LOCAL_READ"))
                .put(JSONObject().put("id", "W03").put("status", "BLOCKED_LOCAL_READ"))
        ).forEach { forged ->
            assertThrows(IllegalArgumentException::class.java) {
                OwnerGateway.parseLocalWorkers(response().put("results", forged), tasks, 1)
            }
        }
    }

    @Test fun workerRequestRejectsUnsupportedOrDuplicatedOperationsBeforeSending() {
        val tasks = workerTasks()
        assertThrows(IllegalArgumentException::class.java) {
            OwnerGateway.workerTaskDigest(tasks.put(JSONObject()
                .put("id", "W01").put("kind", "status").put("args", JSONObject())))
        }
        assertThrows(IllegalArgumentException::class.java) {
            OwnerGateway.workerTaskDigest(org.json.JSONArray().put(JSONObject()
                .put("id", "W01").put("kind", "github.merge").put("args", JSONObject())))
        }
        assertThrows(IllegalArgumentException::class.java) {
            OwnerGateway.workerTaskDigest(org.json.JSONArray().put(JSONObject()
                .put("id", "W01").put("kind", "memory.search")
                .put("args", JSONObject().put("query", "hafıza").put("limit", "5"))))
        }
    }

    @Test fun noModelsAreVerifiedAtProcessStart() {
        OwnerGateway.clear()
        assertTrue(OwnerGateway.verifiedModels("https://server.example", "Mehmet").isEmpty())
    }
}
