package com.example.gptasistan

enum class OmegaModelReadiness { READY, NEEDS_KEY, NEEDS_ENDPOINT }
data class OmegaModelEntry(val provider: OmegaModelProvider, val effectiveModelId: String, val readiness: OmegaModelReadiness) {
    val label: String get() = when (readiness) {
        OmegaModelReadiness.READY -> "● " + provider.title + " · " + effectiveModelId
        OmegaModelReadiness.NEEDS_KEY -> "○ " + provider.title + " · " + effectiveModelId + " (API anahtarı gerekli)"
        OmegaModelReadiness.NEEDS_ENDPOINT -> "○ " + provider.title + " · " + effectiveModelId + " (yerel uç nokta gerekli)"
    }
}
/** Katalogdaki TÜM modelleri her zaman döndürür; anahtar/uç nokta yoksa READY yerine soluk durum işaretler. Yetki kararı vermez. */
object OmegaModelListProvider {
    fun list(
        hasKey: (OmegaModelProvider) -> Boolean,
        hasEndpoint: (OmegaModelProvider) -> Boolean,
        modelOverride: (OmegaModelProvider) -> String?
    ): List<OmegaModelEntry> = OmegaModelCatalog.providers.map { p ->
        val id = modelOverride(p)?.trim()?.takeIf { it.isNotBlank() } ?: p.modelId
        val state = when {
            p.requiresSecret && !hasKey(p) -> OmegaModelReadiness.NEEDS_KEY
            p.kind == OmegaProviderKind.LOCAL_OPENAI_COMPATIBLE && !hasEndpoint(p) -> OmegaModelReadiness.NEEDS_ENDPOINT
            else -> OmegaModelReadiness.READY
        }
        OmegaModelEntry(p, id, state)
    }
}
