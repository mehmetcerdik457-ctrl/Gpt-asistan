package com.example.gptasistan

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/** No provider key, redirect, implicit memory upload, or unverified model is accepted here. */
object OwnerGateway {
    data class Model(val id: String, val provider: String, val verifiedAt: Long, val latencyMs: Long)
    private data class Registry(val base: String, val owner: String, val models: List<Model>)
    @Volatile private var registry: Registry? = null

    fun validBase(base: String): Boolean = ModelGateway.valid(base) && try {
        val url = URL(base)
        url.path in listOf("", "/") && url.port != 0
    } catch (_: Exception) { false }

    fun clear() { registry = null }

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

    fun reply(context: Context, base: String, model: String, question: String): String {
        val owner = context.getSharedPreferences("kral_model", Context.MODE_PRIVATE).getString("owner_id", "").orEmpty()
        val chosen = verifiedModels(base, owner).singleOrNull { it.id == model }
            ?: throw SecurityException("MODEL_NOT_VERIFIED")
        val body = JSONObject().put("message", question).put("model", chosen.id).put("include_memory", false)
        val result = request(base, OmegaEnvelope.CHAT, owner, body)
        return parseReply(result, chosen)
    }

    /** Explicit owner-signed read-only local batch. No model or external writes. */
    fun localWorkers(context: Context, base: String, tasks: JSONArray, maxParallel: Int = 4): JSONArray {
        require(tasks.length() in 1..50 && maxParallel in 1..4)
        val owner = context.getSharedPreferences("kral_model", Context.MODE_PRIVATE)
            .getString("owner_id", "").orEmpty()
        val body = JSONObject().put("tasks", tasks).put("max_parallel", maxParallel)
        return parseLocalWorkers(request(base, OmegaEnvelope.WORKERS, owner, body), tasks, maxParallel)
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

    internal fun parseReply(result: JSONObject, selected: Model): String {
        require(result.getString("contract") == OmegaEnvelope.CONTRACT)
        require(result.getString("model") == selected.id && result.getString("provider") == selected.provider)
        require(integer(result, "latency_ms") >= 0)
        val answer = result.get("text")
        require(answer is String && answer.isNotBlank() && answer.length <= 32000)
        return answer
    }

    private fun integer(value: JSONObject, key: String): Long {
        val number = value.get(key)
        require(number is Int || number is Long)
        return (number as Number).toLong()
    }

    private fun request(base: String, path: String, owner: String, json: JSONObject): JSONObject {
        require(validBase(base) && OmegaEnvelope.validOwner(owner))
        val body = json.toString().toByteArray(Charsets.UTF_8)
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
            require(connection.responseCode == 200) { "OWNER_REQUEST_DENIED" }
            JSONObject(ModelGateway.readJsonResponse(connection))
        } finally { connection.disconnect() }
    }
}
