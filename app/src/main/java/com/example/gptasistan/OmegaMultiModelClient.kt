package com.example.gptasistan

import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** Provider-specific HTTPS adapters. Secrets are passed from Android Keystore and never logged. */
object OmegaMultiModelClient {
    fun chat(provider: OmegaModelProvider, apiKey: String?, prompt: String, systemPrompt: String, customEndpoint: String? = null): String {
        require(prompt.isNotBlank() && prompt.length <= 16000)
        if (provider.requiresSecret) require(!apiKey.isNullOrBlank() && apiKey.length <= 4096)
        val endpoint = customEndpoint?.trim()?.takeIf { it.isNotBlank() } ?: provider.endpoint
        if (provider.kind == OmegaProviderKind.LOCAL_OPENAI_COMPATIBLE) {
            require(endpoint.startsWith("http://127.0.0.1") || endpoint.startsWith("http://localhost") ||
                endpoint.startsWith("https://")) { "LOCAL_ENDPOINT_MUST_BE_LOOPBACK_OR_HTTPS" }
        }
        return when (provider.kind) {
            OmegaProviderKind.ANTHROPIC -> anthropic(provider, apiKey!!, prompt, systemPrompt)
            OmegaProviderKind.GEMINI -> gemini(provider, apiKey!!, prompt, systemPrompt)
            OmegaProviderKind.OPENAI_COMPATIBLE,
            OmegaProviderKind.LOCAL_OPENAI_COMPATIBLE -> openAiCompatible(provider, apiKey, prompt, systemPrompt, endpoint)
        }
    }

    private fun openAiCompatible(p: OmegaModelProvider, key: String?, prompt: String, system: String, endpoint: String): String {
        val payload = JSONObject().put("model", p.modelId).put("messages", JSONArray()
            .put(JSONObject().put("role", "system").put("content", system))
            .put(JSONObject().put("role", "user").put("content", prompt)))
        return request(endpoint, payload, mapOf("Authorization" to if (key.isNullOrBlank()) "" else "Bearer $key"))
            .let { json ->
                json.optJSONArray("choices")?.optJSONObject(0)?.optJSONObject("message")
                    ?.optString("content")?.trim()?.takeIf { it.isNotBlank() }
                    ?: throw IOException("PROVIDER_EMPTY_RESPONSE")
            }
    }

    private fun anthropic(p: OmegaModelProvider, key: String, prompt: String, system: String): String {
        val payload = JSONObject().put("model", p.modelId).put("max_tokens", 4096)
            .put("system", system)
            .put("messages", JSONArray().put(JSONObject().put("role", "user").put("content", prompt)))
        val json = request(p.endpoint, payload, mapOf(
            "x-api-key" to key,
            "anthropic-version" to "2023-06-01"
        ))
        val blocks = json.optJSONArray("content") ?: throw IOException("PROVIDER_EMPTY_RESPONSE")
        val answer = buildString {
            for (i in 0 until blocks.length()) {
                val block = blocks.optJSONObject(i) ?: continue
                if (block.optString("type") == "text") append(block.optString("text"))
            }
        }.trim()
        return answer.takeIf { it.isNotBlank() } ?: throw IOException("PROVIDER_EMPTY_RESPONSE")
    }

    private fun gemini(p: OmegaModelProvider, key: String, prompt: String, system: String): String {
        val endpoint = "${p.endpoint}/${p.modelId}:generateContent"
        val payload = JSONObject()
            .put("systemInstruction", JSONObject().put("parts", JSONArray().put(JSONObject().put("text", system))))
            .put("contents", JSONArray().put(JSONObject().put("role", "user")
                .put("parts", JSONArray().put(JSONObject().put("text", prompt)))))
        val json = request(endpoint, payload, mapOf("x-goog-api-key" to key))
        val candidates = json.optJSONArray("candidates") ?: throw IOException("PROVIDER_EMPTY_RESPONSE")
        val parts = candidates.optJSONObject(0)?.optJSONObject("content")?.optJSONArray("parts")
            ?: throw IOException("PROVIDER_EMPTY_RESPONSE")
        val answer = buildString {
            for (i in 0 until parts.length()) append(parts.optJSONObject(i)?.optString("text").orEmpty())
        }.trim()
        return answer.takeIf { it.isNotBlank() } ?: throw IOException("PROVIDER_EMPTY_RESPONSE")
    }

    private fun request(endpoint: String, payload: JSONObject, headers: Map<String, String>): JSONObject {
        val connection = (URL(endpoint).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 15000
            readTimeout = 60000
            doOutput = true
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            setRequestProperty("Accept", "application/json")
            headers.forEach { (name, value) -> if (value.isNotBlank()) setRequestProperty(name, value) }
        }
        try {
            connection.outputStream.use { it.write(payload.toString().toByteArray(Charsets.UTF_8)) }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val body = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (status !in 200..299) throw IOException("PROVIDER_HTTP_$status")
            return try { JSONObject(body) } catch (_: Exception) { throw IOException("PROVIDER_INVALID_RESPONSE") }
        } finally {
            connection.disconnect()
        }
    }
}
