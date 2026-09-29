package com.mehmetcerdik.ownerai;

import org.junit.Test;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public final class SecureSecretsPolicyTest {
    @Test public void encryptedMemoryMarkerIsStrict() {
        assertTrue(SecureSecrets.isEncryptedMemoryBlob("enc:v1:aXY=:Y2lwaGVy"));
        assertFalse(SecureSecrets.isEncryptedMemoryBlob("plaintext owner memory"));
        assertFalse(SecureSecrets.isEncryptedMemoryBlob("enc:v1::cipher"));
        assertFalse(SecureSecrets.isEncryptedMemoryBlob(null));
    }
}
