package com.mehmetcerdik.ownerai;

import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;

import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.util.Locale;

import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

final class AuditIntegrity {
    private static final String KEYSTORE = "AndroidKeyStore";
    private static final String ALIAS = "mehmet_owner_audit_hmac_v1";

    private AuditIntegrity() {}

    private static SecretKey key() throws Exception {
        KeyStore ks = KeyStore.getInstance(KEYSTORE);
        ks.load(null);
        if (ks.containsAlias(ALIAS)) {
            return ((KeyStore.SecretKeyEntry) ks.getEntry(ALIAS, null)).getSecretKey();
        }
        KeyGenerator g = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_HMAC_SHA256, KEYSTORE);
        g.init(new KeyGenParameterSpec.Builder(
                ALIAS, KeyProperties.PURPOSE_SIGN | KeyProperties.PURPOSE_VERIFY)
                .setDigests(KeyProperties.DIGEST_SHA256)
                .build());
        return g.generateKey();
    }

    static String recordHash(long sequence, long timestamp, String event, String status,
                             String detailHash, String previousHash) {
        return sha256(sequence + "|" + timestamp + "|" + safe(event) + "|" + safe(status)
                + "|" + safe(detailHash) + "|" + safe(previousHash));
    }

    static String mac(String recordHash) {
        try {
            Mac m = Mac.getInstance("HmacSHA256");
            m.init(key());
            return hex(m.doFinal(safe(recordHash).getBytes(StandardCharsets.UTF_8)));
        } catch (Exception e) {
            throw new IllegalStateException("AUDIT_HMAC_FAILED", e);
        }
    }

    static boolean verifyMac(String recordHash, String expected) {
        try {
            byte[] a = hexBytes(mac(recordHash));
            byte[] b = hexBytes(expected);
            return MessageDigest.isEqual(a, b);
        } catch (Exception e) {
            return false;
        }
    }

    static String sha256(String value) {
        try {
            return hex(MessageDigest.getInstance("SHA-256").digest(safe(value).getBytes(StandardCharsets.UTF_8)));
        } catch (Exception e) {
            throw new IllegalStateException("SHA256_FAILED", e);
        }
    }

    private static String safe(String s) { return s == null ? "" : s; }

    private static String hex(byte[] data) {
        StringBuilder b = new StringBuilder(data.length * 2);
        for (byte x : data) b.append(String.format(Locale.ROOT, "%02x", x & 0xff));
        return b.toString();
    }

    private static byte[] hexBytes(String s) {
        if (s == null || (s.length() & 1) != 0) throw new IllegalArgumentException("BAD_HEX");
        byte[] out = new byte[s.length() / 2];
        for (int i = 0; i < out.length; i++) out[i] = (byte) Integer.parseInt(s.substring(i * 2, i * 2 + 2), 16);
        return out;
    }
}
