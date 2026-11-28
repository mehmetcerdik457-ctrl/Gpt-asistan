package com.example.gptasistan
import org.junit.Assert.*
import org.junit.Test

class OmegaModelListProviderTest {
    @Test fun listsAllModelsEvenWithoutKeys() {
        val l = OmegaModelListProvider.list({ false }, { false }, { null })
        println("ModelListProvider(no key): " + l.joinToString(" | ") { it.label })
        assertEquals(8, l.size)
        assertTrue(l.map { it.provider.id }.containsAll(listOf("openai","gemini","anthropic","xai","groq","llama","mistral","gemma")))
        assertEquals(0, l.count { it.readiness == OmegaModelReadiness.READY })
    }
    @Test fun mockKeysMarkProvidersReadyAndOverrideApplies() {
        val l = OmegaModelListProvider.list({ it.id == "xai" || it.id == "gemini" }, { it.id == "llama" }, { if (it.id == "xai") "grok-ultra-test" else null })
        println("ModelListProvider(mock keys): " + l.joinToString(" | ") { it.label })
        val ready = l.filter { it.readiness == OmegaModelReadiness.READY }.map { it.provider.id }.toSet()
        assertEquals(setOf("xai", "gemini", "llama"), ready)
        assertEquals("grok-ultra-test", l.first { it.provider.id == "xai" }.effectiveModelId)
        assertEquals("openai", l.first { it.readiness == OmegaModelReadiness.NEEDS_KEY }.provider.id)
    }
}
