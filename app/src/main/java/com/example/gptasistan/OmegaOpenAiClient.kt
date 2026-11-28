package com.example.gptasistan

import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * Direct OpenAI Chat Completions adapter.
 * The API key is supplied from Android Keystore at call time and is never persisted or logged here.
 */
object OmegaOpenAiClient {
    const val MODEL = "gpt-4.1-mini"
    private const val ENDPOINT = "https://api.openai.com/v1/chat/completions"

    @Throws(IOException::class)
    fun chat(apiKey: String, prompt: String): String {
        require(apiKey.isNotBlank() && apiKey.length <= 4096)
        require(prompt.isNotBlank() && prompt.length <= 16000)
        val messages = JSONArray()
            .put(JSONObject().put("role", "system").put("content", OmegaSystemPolicy.SYSTEM_GUIDANCE))
            .put(JSONObject().put("role", "user").put("content", prompt))
        val payload = JSONObject()
            .put("model", MODEL)
            .put("messages", messages)
        val connection = (URL(ENDPOINT).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 15000
            readTimeout = 45000
            doOutput = true
            setRequestProperty("Authorization", "Bearer $apiKey")
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            setRequestProperty("Accept", "application/json")
        }
        try {
            connection.outputStream.use { stream ->
                stream.write(payload.toString().toByteArray(Charsets.UTF_8))
            }
            val status = connection.responseCode
            val responseStream = if (status in 200..299) connection.inputStream else connection.errorStream
            val responseText = responseStream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (status !in 200..299) throw IOException("OPENAI_HTTP_$status")
            val response = JSONObject(responseText)
            val answer = response.optJSONArray("choices")
                ?.optJSONObject(0)
                ?.optJSONObject("message")
                ?.optString("content")
                ?.trim()
            if (answer.isNullOrBlank()) throw IOException("OPENAI_EMPTY_RESPONSE")
            return answer.take(16000)
        } catch (error: IOException) {
            throw error
        } catch (_: Exception) {
            throw IOException("OPENAI_INVALID_RESPONSE")
        } finally {
            connection.disconnect()
        }
    }
}
