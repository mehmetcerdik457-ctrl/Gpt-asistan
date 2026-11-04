package com.example.gptasistan

import org.json.JSONArray
import org.json.JSONObject

/** Presentation of verified task results; model text is never an executable command. */
internal object ExpertTasks {
    fun validTaskId(value: String) = value.matches(Regex("[a-f0-9]{32}"))

    fun report(task: OwnerGateway.Task): String = buildString {
        val label = when (task.status) {
            "queued" -> "sırada"
            "running" -> "işleniyor; iptal isteği varsa sonuç bastırılır"
            "completed" -> "tamamlandı"
            "failed" -> "başarısız"
            "cancelled" -> "iptal edildi"
            "awaiting_approval" -> "onay bekliyor; çalıştırılmadı"
            "approved_not_executed" -> "onay kaydedildi; çalıştırılmadı"
            else -> "bilinmeyen durum"
        }
        append("Uzman görevi: $label\nGörev kimliği: ${task.taskId}")
        append("\nİstek SHA-256: ${task.requestSha256}")
        task.error?.let { append("\nHata: $it") }
        task.result?.let { append("\n\nUzman önerisi:\n$it") }
        task.resultSha256?.let { append("\nYanıt SHA-256: $it") }
        task.responseId?.let { append("\nYanıt kimliği: $it") }
        task.providerRequestId?.let { append("\nSağlayıcı istek kimliği: $it") }
        append("\nAraç veya dış işlem yürütülmedi. Durum yenileme elle yapılır.")
    }

    /** Two bounded reads from the configured owner server; no live model probe. */
    fun statusBatch(): JSONArray = JSONArray()
        .put(JSONObject().put("id", "W01").put("kind", "status").put("args", JSONObject()))
        .put(JSONObject().put("id", "W02").put("kind", "models.cached").put("args", JSONObject()))
}
