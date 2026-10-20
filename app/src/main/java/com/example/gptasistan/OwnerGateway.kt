package com.example.gptasistan

import android.content.Context
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
