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
        assertNotEquals(a, AuditIntegrity.recordHash(2, 1000, "EVENT", "PASS", "detail", "GENESIS"));
        assertNotEquals(a, AuditIntegrity.recordHash(1, 1001, "EVENT", "PASS", "detail", "GENESIS"));
        assertNotEquals(a, AuditIntegrity.recordHash(1, 1000, "OTHER_EVENT", "PASS", "detail", "GENESIS"));
        assertNotEquals(a, AuditIntegrity.recordHash(1, 1000, "EVENT", "PASS", "other-detail", "GENESIS"));
    }

    @Test public void chainedRecordFailsIfAnyPriorRecordHashChanges() {
        String r1 = AuditIntegrity.recordHash(1, 1000, "OWNER_AUTH", "PASS", "d1", "GENESIS");
        String r2 = AuditIntegrity.recordHash(2, 1001, "TOOL", "PASS", "d2", r1);
        String tamperedR1 = AuditIntegrity.recordHash(1, 1000, "OWNER_AUTH", "FAIL", "d1", "GENESIS");
        String tamperedR2 = AuditIntegrity.recordHash(2, 1001, "TOOL", "PASS", "d2", tamperedR1);
        assertNotEquals(r1, tamperedR1);
        assertNotEquals(r2, tamperedR2);
    }
}
