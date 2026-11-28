package com.example.gptasistan

enum class OmegaRouteIntent { CODING, GENERAL, IMAGE_ANALYSIS }

data class OmegaRouteSelection(
    val provider: OmegaModelProvider?,
    val intent: OmegaRouteIntent,
    val reason: String
)

/**
 * Deterministic, local-first provider router. It never silently falls back to an
 * unconfigured provider. Image routing is blocked until chat transport accepts
 * actual image bytes instead of pretending text is an image.
 */
object OmegaAutoRouter {
    fun classify(text: String): OmegaRouteIntent {
        val value = text.lowercase()
        return when {
            listOf("resmi analiz", "fotoğrafı analiz", "görseli incele", "image analysis",
                "what is in this picture", "bu fotoğrafta").any(value::contains) ->
                OmegaRouteIntent.IMAGE_ANALYSIS
            listOf("kod yaz", "kodla", "bug düzelt", "refactor", "python", "kotlin",
                "java", "fonksiyon yaz", "web sitesi yap", "uygulama geliştir").any(value::contains) ->
                OmegaRouteIntent.CODING
            else -> OmegaRouteIntent.GENERAL
        }
    }

    fun select(text: String, configuredProviders: List<OmegaModelProvider>): OmegaRouteSelection {
        val intent = classify(text)
        if (intent == OmegaRouteIntent.IMAGE_ANALYSIS) {
            return OmegaRouteSelection(null, intent,
                "IMAGE_INPUT_NOT_SUPPORTED: Bu sohbet aktarımı henüz görsel dosya baytlarını modele göndermiyor.")
        }
        val order = when (intent) {
            OmegaRouteIntent.CODING -> listOf("anthropic", "openai", "xai", "gemini", "groq", "llama", "mistral", "gemma")
            OmegaRouteIntent.GENERAL -> listOf("openai", "gemini", "anthropic", "xai", "groq", "llama", "mistral", "gemma")
            OmegaRouteIntent.IMAGE_ANALYSIS -> emptyList()
        }
        val selected = order.firstNotNullOfOrNull { id -> configuredProviders.firstOrNull { it.id == id } }
        return OmegaRouteSelection(selected, intent,
            if (selected == null) "NO_CONFIGURED_PROVIDER: Otomatik mod için uygun API anahtarı veya yerel uç nokta bulunamadı."
            else "AUTO_ROUTED_${intent.name}_TO_${selected.id.uppercase()}")
    }
}
