package com.mehmetcerdik.ownerai;

import org.junit.Test;
import static org.junit.Assert.*;

public final class SecureSecretsPolicyTest {
    @Test public void encryptedMemoryMarkersAreStrict() {
        assertTrue(SecureSecrets.isEncryptedMemoryBlob("enc:v1:aXY=:Y2lwaGVy"));
        assertTrue(SecureSecrets.isEncryptedMemoryBlob("enc:v2:aXY=:Y2lwaGVy"));
        assertFalse(SecureSecrets.isEncryptedMemoryBlob("plaintext owner memory"));
        assertFalse(SecureSecrets.isEncryptedMemoryBlob("enc:v2::cipher"));
        assertFalse(SecureSecrets.isEncryptedMemoryBlob(null));
    }
}
