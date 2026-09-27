package com.mehmetcerdik.ownerai;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import java.nio.charset.StandardCharsets;
import java.security.KeyStore;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class SecureSecrets {
    private static final String KEYSTORE = "AndroidKeyStore";
    private static final String PROVIDER_ALIAS = "mehmet_owner_provider_secret_v1";
    private static final String MEMORY_ALIAS = "mehmet_owner_memory_v1";
    private static final String MEMORY_PREFIX = "enc:v1:";
    private static final String PREFS = "owner_secure_config";
    private static final String KEY_SECRET = "provider_secret";

    private SecureSecrets() {}

    private static SecretKey getOrCreateKey(String alias) throws Exception {
        KeyStore ks = KeyStore.getInstance(KEYSTORE);
        ks.load(null);
        if (ks.containsAlias(alias)) {
            return ((KeyStore.SecretKeyEntry) ks.getEntry(alias, null)).getSecretKey();
        }
        KeyGenerator kg = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE);
        kg.init(new KeyGenParameterSpec.Builder(
                alias,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build());
        return kg.generateKey();
    }

    public static void storeProviderSecret(Context c, String secret) {
        try {
            if (secret == null || secret.trim().isEmpty()) {
                c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().remove(KEY_SECRET).apply();
                return;
            }
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey(PROVIDER_ALIAS));
            byte[] encrypted = cipher.doFinal(secret.getBytes(StandardCharsets.UTF_8));
            String encoded = Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP) + ":" +
                    Base64.encodeToString(encrypted, Base64.NO_WRAP);
            c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(KEY_SECRET, encoded).apply();
        } catch (Exception e) {
            throw new IllegalStateException("KEYSTORE_WRITE_FAILED", e);
        }
    }

    static String encryptMemory(String plaintext) {
        try {
            if (plaintext == null) throw new IllegalArgumentException("MEMORY_NULL");
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey(MEMORY_ALIAS));
            byte[] encrypted = cipher.doFinal(plaintext.getBytes(StandardCharsets.UTF_8));
            return MEMORY_PREFIX +
                    Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP) + ":" +
                    Base64.encodeToString(encrypted, Base64.NO_WRAP);
        } catch (Exception e) {
            throw new IllegalStateException("MEMORY_ENCRYPT_FAILED", e);
        }
    }

    static String decryptMemory(String encoded) {
        if (!isEncryptedMemoryBlob(encoded)) return null;
        try {
            String[] parts = encoded.split(":", 4);
            byte[] iv = Base64.decode(parts[2], Base64.NO_WRAP);
            byte[] encrypted = Base64.decode(parts[3], Base64.NO_WRAP);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(MEMORY_ALIAS), new GCMParameterSpec(128, iv));
            return new String(cipher.doFinal(encrypted), StandardCharsets.UTF_8);
        } catch (Exception e) {
            return null;
        }
    }

    static boolean isEncryptedMemoryBlob(String value) {
        if (value == null || !value.startsWith(MEMORY_PREFIX)) return false;
        String[] parts = value.split(":", 4);
        return parts.length == 4 && !parts[2].isEmpty() && !parts[3].isEmpty();
    }

    public static String loadProviderSecret(Context c) {
        try {
            SharedPreferences p = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            String encoded = p.getString(KEY_SECRET, "");
            if (encoded == null || encoded.isEmpty()) return "";
            String[] parts = encoded.split(":", 2);
            if (parts.length != 2) return "";
            byte[] iv = Base64.decode(parts[0], Base64.NO_WRAP);
            byte[] encrypted = Base64.decode(parts[1], Base64.NO_WRAP);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(PROVIDER_ALIAS), new GCMParameterSpec(128, iv));
            return new String(cipher.doFinal(encrypted), StandardCharsets.UTF_8);
        } catch (Exception e) {
            return "";
        }
    }
}
