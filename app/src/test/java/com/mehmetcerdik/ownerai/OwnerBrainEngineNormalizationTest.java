package com.mehmetcerdik.ownerai;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public final class OwnerBrainEngineNormalizationTest {
    @Test public void turkishDottedCapitalIInCihatIsStable() {
        assertEquals("cihat aç", OwnerBrainEngine.normalizeCommandText("CİHAT aç"));
    }

    @Test public void turkishDotlessIAndAsciiCommandsConverge() {
        assertEquals("cihat ac", OwnerBrainEngine.normalizeCommandText("CIHAT AC"));
        assertEquals("cihat ac", OwnerBrainEngine.normalizeCommandText("CıHAT AC"));
    }
}
