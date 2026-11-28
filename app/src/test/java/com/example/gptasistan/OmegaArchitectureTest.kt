package com.example.gptasistan

import org.junit.Assert.*
import org.junit.Test

class OmegaArchitectureTest {
    @Test fun providerCatalogCoversCloudAndLocalFamilies() {
        assertTrue(OmegaModelCatalog.providers.map { it.id }.containsAll(
            listOf("openai", "gemini", "anthropic", "xai", "groq", "llama", "mistral", "gemma")
        ))
    }
    @Test fun connectorsFailClosed() {
        assertEquals(OmegaConnectorState.DISABLED_UNTIL_SANDBOXED, OmegaConnectorCatalog.connectors.first { it.id == "python" }.state)
        assertEquals(OmegaConnectorState.OAUTH_REQUIRED, OmegaConnectorCatalog.connectors.first { it.id == "github" }.state)
        assertEquals(OmegaConnectorState.OAUTH_REQUIRED, OmegaConnectorCatalog.connectors.first { it.id == "google_drive" }.state)
    }
    @Test fun externalEffectsRequireApproval() {
        assertTrue(OmegaCapabilityPolicy.requiresExplicitApproval("github.write"))
        assertFalse(OmegaCapabilityPolicy.requiresExplicitApproval("chat.read"))
    }
    @Test fun promptDefinesTrustBoundary() {
        assertTrue(OmegaSystemPolicy.SYSTEM_GUIDANCE.contains("güvenilmeyen veri"))
        assertTrue(OmegaSystemPolicy.SYSTEM_GUIDANCE.contains("Model önerir"))
    }
    @Test fun agentHubRoutesCodingFileAnalysisAndPlanning() {
        assertEquals(OmegaAgentTask.CODING, OmegaAgentHub.route("Kotlin ile kod yaz").task)
        assertEquals(OmegaAgentTask.FILE_ANALYSIS, OmegaAgentHub.route("Bu PDF dosyasını analiz et").task)
        assertEquals(OmegaAgentTask.PLANNING, OmegaAgentHub.route("Proje yol haritası planla").task)
    }
    @Test fun explicitAgentModeOverridesAutoDetection() {
        assertEquals(OmegaAgentTask.CODING, OmegaAgentHub.route("Merhaba", "coding").task)
    }
}
