package com.mehmetcerdik.ownerai;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public final class OwnerFeatureConfigTest {
    @Test public void manualModelWinsWhenAutoOff() {
        assertEquals("manual", OwnerFeatureConfig.routeModel(false, false, "manual", "fast", "reason", "deep", "analyze"));
    }

    @Test public void deepResearchUsesDedicatedSlot() {
        assertEquals("deep", OwnerFeatureConfig.routeModel(true, true, "manual", "fast", "reason", "deep", "hello"));
    }

    @Test public void reasoningHeavyRequestUsesReasoningSlot() {
        assertEquals("reason", OwnerFeatureConfig.routeModel(true, false, "manual", "fast", "reason", "deep", "Lütfen bu kodu analiz et"));
    }

    @Test public void ordinaryAutoRequestUsesFastSlot() {
        assertEquals("fast", OwnerFeatureConfig.routeModel(true, false, "manual", "fast", "reason", "deep", "Merhaba"));
    }

    @Test public void unsupportedReasoningEffortFailsToProviderDefault() {
        assertEquals("provider_default", OwnerFeatureConfig.normalizeReasoningEffort("ultra"));
        assertEquals("xhigh", OwnerFeatureConfig.normalizeReasoningEffort("xhigh"));
    }

    @Test public void longInputIsReasoningHeavy() {
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < 1300; i++) b.append('x');
        assertTrue(OwnerFeatureConfig.looksReasoningHeavy(b.toString()));
        assertFalse(OwnerFeatureConfig.looksReasoningHeavy("hello"));
    }
}
