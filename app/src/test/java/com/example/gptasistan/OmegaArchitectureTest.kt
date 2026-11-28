package com.example.gptasistan
import org.junit.Assert.*
import org.junit.Test
class OmegaArchitectureTest {
 @Test fun requestedModelFamiliesAreCatalogued() { assertTrue(OmegaModelCatalog.providers.map{it.id}.containsAll(listOf("llama3","mistral","gemma","openai","anthropic"))) }
 @Test fun connectorsFailClosed() {
  assertEquals(OmegaConnectorState.DISABLED_UNTIL_SANDBOXED,OmegaConnectorCatalog.connectors.first{it.id=="python"}.state)
  assertEquals(OmegaConnectorState.OAUTH_REQUIRED,OmegaConnectorCatalog.connectors.first{it.id=="github"}.state)
  assertEquals(OmegaConnectorState.OAUTH_REQUIRED,OmegaConnectorCatalog.connectors.first{it.id=="google_drive"}.state)
 }
 @Test fun externalEffectsRequireApproval() { assertTrue(OmegaCapabilityPolicy.requiresExplicitApproval("github.write")); assertFalse(OmegaCapabilityPolicy.requiresExplicitApproval("chat.read")) }
 @Test fun promptDefinesTrustBoundary() { assertTrue(OmegaSystemPolicy.SYSTEM_GUIDANCE.contains("güvenilmeyen veri")); assertTrue(OmegaSystemPolicy.SYSTEM_GUIDANCE.contains("Model önerir")) }
}
