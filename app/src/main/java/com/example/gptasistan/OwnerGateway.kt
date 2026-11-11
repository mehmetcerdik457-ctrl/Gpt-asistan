package com.example.gptasistan

import android.content.Context
import com.example.gptasistan.billing.PlayPurchaseSubmission
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID
import java.io.ByteArrayOutputStream
import java.io.IOException

/** No provider key, redirect, implicit memory upload, or unverified model is accepted here. */
object OwnerGateway {
    data class Model(val id: String, val provider: String, val verifiedAt: Long, val latencyMs: Long)
    data class Reply(
        val text: String, val model: String, val provider: String,
        val responseId: String, val providerRequestId: String?,
        val clientRequestId: String, val latencyMs: Long,
    )
    internal class GatewayFailure(
        val httpStatus: Int, val errorCode: String,
        val providerRequestId: String?, val providerHttpStatus: Int?,
        val providerErrorCode: String?, val retryable: Boolean,
        val retryAfterSeconds: Long?,
    ) : IOException(errorCode)
    data class Task(
        val taskId: String, val status: String, val requestSha256: String,
        val result: String?, val resultSha256: String?, val responseId: String?,
        val providerRequestId: String?, val providerHttpStatus: Int?,
        val providerErrorCode: String?, val retryable: Boolean,
        val retryAfterSeconds: Long?, val error: String?,
        val clientRequestId: String?,
    )
    private data class Registry(val base: String, val owner: String, val models: List<Model>)
    @Volatile private var registry: Registry? = null

    fun validBase(base: String): Boolean = ModelGateway.valid(base) && try {
        val url = URL(base)
        url.path in listOf("", "/") && url.port != 0
    } catch (_: Exception) { false }

    fun clear() { registry = null }

    /**
     * Fetches the server-generated opaque Google Play billing account ID.
     * Call on a worker thread; returns NO HMAC secret, owner ID or access token.
     * The backend remains disabled unless separately provisioned and approved.
     */
    fun playAccountId(context: Context, base: String): String {
        val owner = configuredPlayOwner(context, base)
        return parsePlayAccountId(request(base, OmegaEnvelope.PLAY_ACCOUNT, owner, JSONObject()))
    }

    /**
     * Submits only productId and purchaseToken via the existing dual-P256
     * authenticated transport, with the identity derived from Android Keystore.
     * Call on a worker thread. A 200 HTTP response alone is NEVER entitlement.
     */
    fun verifyPlayPurchase(
        context: Context, base: String, purchase: PlayPurchaseSubmission
    ): Boolean {
        val owner = configuredPlayOwner(context, base)
        require(purchase.validate(context.packageName)) { "PLAY_SUBMISSION_INVALID" }
        val data = JSONObject().put("productId", purchase.productId)
            .put("purchaseToken", purchase.purchaseToken)
        return parsePlayEntitlement(request(base, OmegaEnvelope.PLAY_VERIFY, owner, data))
    }

    private fun configuredPlayOwner(context: Context, base: String): String {
        val prefs = context.getSharedPreferences("kral_model", Context.MODE_PRIVATE)
        val owner = prefs.getString("owner_id", "").orEmpty()
        val configured = prefs.getString("endpoint", "").orEmpty()
        if (!validBase(base) || !validBase(configured) ||
            configured.trimEnd('/') != base.trimEnd('/') ||
            !OmegaEnvelope.validOwner(owner))
            throw SecurityException("PLAY_BACKEND_SCOPE_NOT_CONFIGURED")
        return owner
    }

    internal fun parsePlayAccountId(result: JSONObject): String {
        require(result.getString("contract") == OmegaEnvelope.CONTRACT)
        val account = result.get("obfuscated_account_id")
        require(account is String && account.matches(Regex("[a-f0-9]{64}")))
        return account
    }

    internal fun parsePlayEntitlement(result: JSONObject): Boolean {
        require(result.getString("contract") == OmegaEnvelope.CONTRACT)
        val entitled = result.get("entitled")
        require(entitled is Boolean)
        val provenance = result.get("verified_by")
        require(provenance is String && provenance == if (entitled) "server_google_play" else "denied")
        return entitled
    }

    fun verifiedModels(base: String, owner: String, now: Long = System.currentTimeMillis() / 1000): List<Model> {
        val cached = registry ?: return emptyList()
        if (cached.base != base.trimEnd('/') || cached.owner != owner) return emptyList()
        return cached.models.filter { it.verifiedAt in (now - 300)..(now + 30) }
    }

    fun models(base: String, owner: String): List<Model> {
        clear()
        val result = request(base, OmegaEnvelope.MODELS, owner, JSONObject())
        val models = parseModels(result, System.currentTimeMillis() / 1000)
        registry = Registry(base.trimEnd('/'), owner, models)
        return models
    }

    internal fun parseModels(result: JSONObject, now: Long): List<Model> {
        require(result.getString("contract") == OmegaEnvelope.CONTRACT)
        val entries = result.getJSONArray("models")
        require(entries.length() <= 32)
        val models = (0 until entries.length()).map { index ->
            val item = entries.getJSONObject(index)
            val model = Model(item.getString("id"), item.getString("provider"),
                integer(item, "verified_at"), integer(item, "latency_ms"))
            require(model.id.isNotBlank() && model.id.length <= 200 && !model.id.any { it.isISOControl() })
            require(model.provider.isNotBlank() && model.provider.length <= 64 && !model.provider.any { it.isISOControl() })
            require(model.verifiedAt in (now - 300)..(now + 30) && model.latencyMs >= 0)
            model
        }
        require(models.map { it.id }.distinct().size == models.size)
        return models
    }

    fun reply(context: Context, base: String, model: String, question: String): String =
        replyWithMetadata(context, base, model, question).text

    fun replyWithMetadata(context: Context, base: String, model: String, question: String): Reply {
        val owner = context.getSharedPreferences("kral_model", Context.MODE_PRIVATE)
            .getString("owner_id", "").orEmpty()
        val chosen = verifiedModels(base, owner).singleOrNull { it.id == model }
            ?: throw SecurityException("MODEL_NOT_VERIFIED")
        val body = chatRequestBody(chosen.id, question)
        val clientRequestId = body.getString("client_request_id")
        val result = request(base, OmegaEnvelope.CHAT, owner, body)
        return parseReplyWithMetadata(result, chosen, clientRequestId)
    }

    internal fun chatRequestBody(model: String, question: String): JSONObject {
        val requestId = UUID.randomUUID().toString().replace("-", "")
        return JSONObject().put("message", question).put("model", model)
            .put("include_memory", false).put("client_request_id", requestId)
            .put("idempotency_key", requestId)
    }

    /** Submit a bounded expert task through the existing dual-P256 owner gateway. */
    fun submitTask(
        context: Context, base: String, model: String, expert: String,
        input: String, requiresApproval: Boolean = false,
    ): Task {
        val owner = context.getSharedPreferences("kral_model", Context.MODE_PRIVATE)
            .getString("owner_id", "").orEmpty()
        return submitTask(context, base,
            prepareTaskSubmission(base, owner, model, expert, input, requiresApproval))
    }

    /** Create once, after selecting a freshly verified model, before the first POST. */
    fun prepareTaskSubmission(
        base: String, owner: String, model: String, expert: String,
        input: String, requiresApproval: Boolean = false,
    ): TaskSubmission {
        if (verifiedModels(base, owner).none { it.id == model })
            throw SecurityException("MODEL_NOT_VERIFIED")
        return TaskSubmission.create(base, owner, model, expert, input, requiresApproval)
    }

    /**
     * Reuses the frozen bytes and logical key only when explicitly called again.
     * A durable server lookup must remain possible after the model cache expires.
     */
    fun submitTask(context: Context, base: String, submission: TaskSubmission): Task {
        val prefs = context.getSharedPreferences("kral_model", Context.MODE_PRIVATE)
        val owner = prefs.getString("owner_id", "").orEmpty()
        val model = prefs.getString("model", "").orEmpty()
        val configuredBase = prefs.getString("endpoint", "").orEmpty()
        if (!submission.matches(base, owner, model) ||
            !submission.matches(configuredBase, owner, model))
            throw SecurityException("TASK_SUBMISSION_SCOPE_CHANGED")
        return parseTaskForSubmission(
            request(base, OmegaEnvelope.TASKS, owner, submission.requestBytes()), submission)
    }

    internal fun parseTaskForSubmission(result: JSONObject, submission: TaskSubmission): Task =
        parseTaskForId(result, submission.requestId).also {
            require(it.clientRequestId == submission.requestId) { "TASK_RESPONSE_CLIENT_ID_MISMATCH" }
            require(it.requestSha256 == submission.requestSha256) { "TASK_RESPONSE_REQUEST_MISMATCH" }
        }

    internal fun taskRequestDigest(model: String, expert: String, input: String): String =
        KralAndroidCore.sha256Hex("""{"expert":${quoteTaskString(expert)},"input":${quoteTaskString(input)},"model":${quoteTaskString(model)}}""")

    fun taskStatus(context: Context, base: String, taskId: String): Task =
        taskAction(context, base, OmegaEnvelope.TASK_STATUS, taskId)

    fun cancelTask(context: Context, base: String, taskId: String): Task =
        taskAction(context, base, OmegaEnvelope.TASK_CANCEL, taskId)

    fun approveTask(context: Context, base: String, taskId: String): Task =
        taskAction(context, base, OmegaEnvelope.TASK_APPROVE, taskId)

    private fun taskAction(context: Context, base: String, path: String, taskId: String): Task {
        require(taskId.matches(Regex("[a-f0-9]{32}")))
        val owner = context.getSharedPreferences("kral_model", Context.MODE_PRIVATE)
            .getString("owner_id", "").orEmpty()
        val body = JSONObject().put("task_id", taskId)
        return parseTaskForId(request(base, path, owner, body), taskId)
    }

    internal fun parseTaskForId(result: JSONObject, expectedTaskId: String): Task =
        parseTask(result).also { require(it.taskId == expectedTaskId) { "TASK_RESPONSE_ID_MISMATCH" } }

    internal fun parseTask(result: JSONObject): Task {
        require(result.getString("contract") == OmegaEnvelope.CONTRACT)
        val taskId = result.get("task_id")
        val status = result.get("status")
        val requestHash = result.get("request_sha256")
        require(taskId is String && taskId.matches(Regex("[a-f0-9]{32}")))
        require(status is String && status in setOf(
            "queued", "running", "completed", "failed", "cancelled",
            "awaiting_approval", "approved_not_executed"
        ))
        require(requestHash is String && requestHash.matches(Regex("[a-f0-9]{64}")))
        val answer = result.opt("result")
        val answerText = if (answer == null || answer == JSONObject.NULL) null else answer as? String
            ?: throw IllegalArgumentException("TASK_RESULT_INVALID")
        require(status != "completed" || answerText != null) { "TASK_COMPLETED_RESULT_MISSING" }
        val answerHash = result.opt("result_sha256")
        val answerDigest = if (answerHash == null || answerHash == JSONObject.NULL) null else answerHash as? String
            ?: throw IllegalArgumentException("TASK_RESULT_HASH_INVALID")
        if (answerText != null) {
            require(status == "completed" && answerText.isNotBlank() && answerText.length <= 32000)
            require(answerDigest != null && answerDigest == KralAndroidCore.sha256Hex(answerText))
        } else require(answerDigest == null)
        fun optionalText(key: String, pattern: Regex? = null): String? {
            val value = result.opt(key)
            if (value == null || value == JSONObject.NULL) return null
            require(value is String && value.length <= 160 && !value.any { it.isISOControl() })
            if (pattern != null) require(value.matches(pattern))
            return value
        }
        val responseId = optionalText("response_id", Regex("[A-Za-z0-9_-]{1,128}"))
        val providerRequestId = optionalText("provider_request_id", Regex("[A-Za-z0-9_-]{1,160}"))
        val providerErrorCode = optionalText("provider_error_code", Regex("[A-Za-z0-9_.-]{1,80}"))
        val error = optionalText("error", Regex("[A-Z0-9_]{1,64}"))
        val clientRequestId = optionalText("client_request_id", Regex("[A-Za-z0-9_-]{1,128}"))
        if (clientRequestId != null) require(clientRequestId == taskId)
        val httpValue = result.opt("provider_http_status")
        val httpStatus = if (httpValue == null || httpValue == JSONObject.NULL) null else {
            require(httpValue is Int || httpValue is Long)
            (httpValue as Number).toInt().also { require(it in 100..599) }
        }
        val retryValue = result.opt("retry_after_seconds")
        val retryAfter = if (retryValue == null || retryValue == JSONObject.NULL) null else {
            require(retryValue is Int || retryValue is Long)
            (retryValue as Number).toLong().also { require(it in 0..86400) }
        }
        val retryable = result.get("retryable")
        require(retryable is Boolean)
        require(integer(result, "tools_executed") == 0L && integer(result, "external_actions") == 0L)
        return Task(taskId, status, requestHash, answerText, answerDigest, responseId,
            providerRequestId, httpStatus, providerErrorCode, retryable, retryAfter, error,
            clientRequestId)
    }

    internal val EXPERTS = setOf(
        "ai-ml-engineer", "android-engineer", "apk-forensic", "chief-engineer",
        "ci-cd-engineer", "cloud-engineer", "code-reviewer", "github-master-ai",
        "mcp-engineer", "release-engineer", "security-auditor", "test-engineer",
    )

    /** Explicit owner-signed read-only local batch. No model or external writes. */
    fun localWorkers(context: Context, base: String, tasks: JSONArray, maxParallel: Int = 4): JSONArray {
        require(tasks.length() in 1..50 && maxParallel in 1..4)
        // Never allow caller mutation to change the signed request while it is in flight.
        val frozenTasks = JSONArray(tasks.toString())
        workerTaskDigest(frozenTasks) // Reject unapproved, malformed or repeated jobs BEFORE signing.
        val owner = context.getSharedPreferences("kral_model", Context.MODE_PRIVATE)
            .getString("owner_id", "").orEmpty()
        val body = JSONObject().put("tasks", frozenTasks).put("max_parallel", maxParallel)
        return parseLocalWorkers(request(base, OmegaEnvelope.WORKERS, owner, body), frozenTasks, maxParallel)
    }

    // Match Python owner_workers.run_batch: sorted JSON keys, UTF-8 and no whitespace.
    // Only the four approved read-only worker kinds are eligible for signed requests.
    internal fun workerTaskDigest(tasks: JSONArray): String {
        require(tasks.length() in 1..50)
        val ids = mutableSetOf<String>()
        val encoded = (0 until tasks.length()).joinToString(",", "[", "]") { index ->
            val task = tasks.getJSONObject(index)
            require(task.length() == 3 && task.has("id") && task.has("kind") && task.has("args"))
            val id = task.get("id")
            val kind = task.get("kind")
            require(id is String && id.matches(Regex("W(0[1-9]|[1-4][0-9]|50)")) && ids.add(id))
            require(kind is String)
            val args = task.getJSONObject("args")
            val encodedArgs = when (kind) {
                "status", "models.cached" -> {
                    require(args.length() == 0)
                    "{}"
                }
                "history.recent" -> {
                    require(args.length() == 1 && args.has("limit"))
                    val count = integer(args, "limit")
                    require(count in 1..5)
                    """{"limit":$count}"""
                }
                "memory.search" -> {
                    require(args.length() == 2 && args.has("query") && args.has("limit"))
                    val query = args.get("query")
                    require(query is String && query.length in 1..200)
                    val count = integer(args, "limit")
                    require(count in 1..10)
                    """{"limit":$count,"query":${quoteTaskString(query)}}"""
                }
                else -> throw IllegalArgumentException("WORKER_KIND_DENIED")
            }
            """{"args":$encodedArgs,"id":${quoteTaskString(id)},"kind":${quoteTaskString(kind)}}"""
        }
        return KralAndroidCore.sha256Hex(encoded)
    }

    private fun quoteTaskString(value: String): String = buildString {
        append('"')
        for (ch in value) {
            when (ch) {
                '"' -> append("\\\"")
                '\\' -> append("\\\\")
                '\b' -> append("\\b")
                '\u000C' -> append("\\f")
                '\n' -> append("\\n")
                '\r' -> append("\\r")
                '\t' -> append("\\t")
                else -> {
                    if (ch.code < 0x20) {
                        val hex = "0123456789abcdef"
                        append("\\u00")
                        append(hex[ch.code ushr 4])
                        append(hex[ch.code and 15])
                    } else append(ch)
                }
            }
        }
        append('"')
    }

    internal fun parseLocalWorkers(result: JSONObject, requestedTasks: JSONArray, maxParallel: Int): JSONArray {
        require(maxParallel in 1..4)
        val expectedDigest = workerTaskDigest(requestedTasks)
        val expectedTasks = requestedTasks.length()
        require(result.getString("contract") == OmegaEnvelope.CONTRACT)
        require(result.getString("mode") == "SIGNED_OWNER_READ_ONLY_LOCAL")
        require(integer(result, "logical_worker_slots") == 50L)
        require(integer(result, "executed_tasks") == expectedTasks.toLong())
        require(integer(result, "parallel_limit") == maxParallel.toLong())
        require(integer(result, "provider_calls") == 0L)
        require(integer(result, "external_actions") == 0L)
        require(integer(result, "automatic_approvals") == 0L)
        val digest = result.get("task_sha256")
        require(digest is String && digest == expectedDigest)
        val entries = result.getJSONArray("results")
        require(entries.length() == expectedTasks)
        for (i in 0 until entries.length()) {
            val item = entries.getJSONObject(i)
            val expectedId = requestedTasks.getJSONObject(i).getString("id")
            val id = item.get("id")
            val status = item.get("status")
            require(id is String && id == expectedId)
            require(status is String && status in setOf("COMPLETED_LOCAL_READ", "BLOCKED_LOCAL_READ", "DENIED"))
        }
        return entries
    }

    internal fun parseReply(result: JSONObject, selected: Model): String =
        parseReplyWithMetadata(result, selected).text

    internal fun parseReplyWithMetadata(
        result: JSONObject, selected: Model, expectedClientRequestId: String? = null,
    ): Reply {
        require(result.getString("contract") == OmegaEnvelope.CONTRACT)
        require(result.getString("model") == selected.id && result.getString("provider") == selected.provider)
        val latency = integer(result, "latency_ms")
        require(latency >= 0)
        val answer = result.get("text")
        require(answer is String && answer.isNotBlank() && answer.length <= 32000)
        val responseId = result.get("response_id") as? String
            ?: throw IllegalArgumentException("RESPONSE_ID_MISSING")
        require(responseId.matches(Regex("[A-Za-z0-9_-]{1,128}")))
        val providerRequestValue = result.opt("provider_request_id")
        val providerRequestId = if (providerRequestValue == null || providerRequestValue == JSONObject.NULL) {
            null
        } else {
            require(providerRequestValue is String && providerRequestValue.matches(Regex("[A-Za-z0-9_-]{1,160}")))
            providerRequestValue
        }
        val clientRequestId = result.get("client_request_id") as? String
            ?: throw IllegalArgumentException("CLIENT_REQUEST_ID_MISSING")
        require(clientRequestId.matches(Regex("[A-Za-z0-9_-]{1,128}")))
        if (expectedClientRequestId != null) require(clientRequestId == expectedClientRequestId)
        return Reply(answer, selected.id, selected.provider, responseId, providerRequestId,
            clientRequestId, latency)
    }

    internal fun parseGatewayFailure(
        httpStatus: Int, rawBody: String?, retryAfterHeader: String? = null,
    ): GatewayFailure {
        require(httpStatus in 100..599)
        val payload = try { rawBody?.takeIf { it.length <= 16384 }?.let { JSONObject(it) } }
            catch (_: Exception) { null }
        fun safeText(key: String, pattern: Regex): String? {
            val value = payload?.opt(key)
            return if (value is String && value.matches(pattern)) value else null
        }
        fun safeNumber(key: String, minimum: Long, maximum: Long): Long? {
            val value = payload?.opt(key)
            if (value !is Int && value !is Long) return null
            return (value as Number).toLong().takeIf { it in minimum..maximum }
        }
        val providerRequestId = safeText("provider_request_id", Regex("[A-Za-z0-9_-]{1,160}"))
        val providerHttpStatus = safeNumber("provider_http_status", 100, 599)?.toInt()
        val providerErrorCode = safeText("provider_error_code", Regex("[A-Za-z0-9_.-]{1,80}"))
        val errorCode = safeText("error", Regex("[A-Z0-9_]{1,64}")) ?: "OWNER_REQUEST_DENIED"
        val retryValue = payload?.opt("retryable")
        val retryable = retryValue is Boolean && retryValue
        val retryAfter = safeNumber("retry_after_seconds", 0, 86400)
            ?: retryAfterHeader?.takeIf { it.matches(Regex("[0-9]{1,5}")) }?.toLongOrNull()
                ?.takeIf { it in 0..86400 }
        return GatewayFailure(httpStatus, errorCode, providerRequestId, providerHttpStatus,
            providerErrorCode, retryable, retryAfter)
    }

    private fun readErrorBody(connection: HttpURLConnection): String? {
        val stream = connection.errorStream ?: return null
        return try {
            val bytes = stream.use { input ->
                val output = ByteArrayOutputStream()
                val buffer = ByteArray(2048)
                var total = 0
                while (true) {
                    val count = input.read(buffer, 0, minOf(buffer.size, 16385 - total))
                    if (count < 0) break
                    if (count == 0) {
                        val next = input.read()
                        if (next < 0) break
                        total++
                        if (total > 16384) return null
                        output.write(next)
                    } else {
                        total += count
                        if (total > 16384) return null
                        output.write(buffer, 0, count)
                    }
                }
                output.toByteArray()
            }
            if (bytes.isEmpty()) null else bytes.toString(Charsets.UTF_8)
        } catch (_: Exception) { null }
    }

    private fun integer(value: JSONObject, key: String): Long {
        val number = value.get(key)
        require(number is Int || number is Long)
        return (number as Number).toLong()
    }

    private fun request(base: String, path: String, owner: String, json: JSONObject): JSONObject {
        return request(base, path, owner, json.toString().toByteArray(Charsets.UTF_8))
    }

    private fun request(base: String, path: String, owner: String, body: ByteArray): JSONObject {
        require(validBase(base) && OmegaEnvelope.validOwner(owner))
        val headers = OwnerIdentity.sign(path, body, owner)
        val connection = URL(base.trimEnd('/') + path).openConnection() as HttpURLConnection
        return try {
            connection.requestMethod = "POST"
            connection.instanceFollowRedirects = false
            connection.connectTimeout = 8000
            connection.readTimeout = 45000
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            connection.setRequestProperty("Accept", "application/json")
            headers.forEach { (name, value) -> connection.setRequestProperty(name, value) }
            connection.outputStream.use { it.write(body) }
            val status = connection.responseCode
            if (status != 200) {
                throw parseGatewayFailure(status, readErrorBody(connection),
                    connection.getHeaderField("Retry-After"))
            }
            JSONObject(ModelGateway.readJsonResponse(connection))
        } finally { connection.disconnect() }
    }
}
