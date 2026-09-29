package com.mehmetcerdik.ownerai;

import org.junit.Test;
import static org.junit.Assert.*;

public final class AuditIntegrityTest {
    @Test public void recordHashIsDeterministicAndChainsPreviousHash() {
        String a = AuditIntegrity.recordHash(1, 1000, "EVENT", "PASS", "detail", "GENESIS");
        String b = AuditIntegrity.recordHash(1, 1000, "EVENT", "PASS", "detail", "GENESIS");
        assertEquals(a, b);
        assertNotEquals(a, AuditIntegrity.recordHash(1, 1000, "EVENT", "FAIL", "detail", "GENESIS"));
        assertNotEquals(a, AuditIntegrity.recordHash(1, 1000, "EVENT", "PASS", "detail", "tampered"));
    }
}
