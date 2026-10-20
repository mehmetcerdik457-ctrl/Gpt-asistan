package com.example.gptasistan

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

// User-configured HTTPS OpenAI-compatible model endpoint. No credentials or
// memories are sent automatically. No redirect, no cleartext, no tool execution.
object ModelGateway {
    fun valid(endpoint: String): Boolean = try {
        val u = URL(endpoint)
        u.protocol == "https" && !u.host.isNullOrBlank() &&
            u.userInfo == null && u.ref == null && u.port in -1..65535
    } catch (_: Exception) { false }

    fun reply(endpoint: String, model: String, question: String): String {
        require(valid(endpoint)) { "Yalnız HTTPS model bağlantısı desteklenir." }
        require(model.isNotBlank()) { "Model adı gerekli." }
        val c = URL(endpoint).openConnection() as HttpURLConnection
        try {
            c.requestMethod = "POST"
            c.connectTimeout = 8000
            c.readTimeout = 30000
            c.instanceFollowRedirects = false
            c.doOutput = true
            c.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            val body = JSONObject()
                .put("model", model)
                .put("stream", false)
                .put("messages", JSONArray().put(JSONObject()
                    .put("role", "user").put("content", question)))
                .toString()
            c.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            if (c.responseCode != 200) return "Model yanıtı alınamadı (HTTP " + c.responseCode + ")."
            val response = c.inputStream.bufferedReader().use { it.readText().take(131072) }
            return JSONObject(response).getJSONArray("choices").getJSONObject(0)
                .getJSONObject("message").getString("content").take(8000)
        } finally { c.disconnect() }
    }
}
