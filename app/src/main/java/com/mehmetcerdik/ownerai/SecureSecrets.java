package com.mehmetcerdik.ownerai;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
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
    private static final String PROVIDER_ALIAS_V2 = "mehmet_owner_provider_secret_v2_auth";
    private static final String MEMORY_ALIAS_V2 = "mehmet_owner_memory_v2";
    private static final String MEMORY_ALIAS_V1 = "mehmet_owner_memory_v1";
    private static final String PROVIDER_PREFIX = "enc:v2:";
    private static final String MEMORY_PREFIX_V2 = "enc:v2:";
    private static final String MEMORY_PREFIX_V1 = "enc:v1:";
    private static final String PREFS = "owner_secure_config";
    private static final String KEY_SECRET_V2 = "provider_secret_v2";
    private static final String KEY_SECRET_LEGACY = "provider_secret";
    private static final int AUTH_VALIDITY_SECONDS = 120;

    private SecureSecrets() {}

    private static SecretKey getOrCreateProviderKey() throws Exception {
        KeyStore ks = KeyStore.getInstance(KEYSTORE);
        ks.load(null);
        if (ks.containsAlias(PROVIDER_ALIAS_V2)) {
            return ((KeyStore.SecretKeyEntry) ks.getEntry(PROVIDER_ALIAS_V2, null)).getSecretKey();
        }
        KeyGenerator kg = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE);
        KeyGenParameterSpec.Builder b = new KeyGenParameterSpec.Builder(
                PROVIDER_ALIAS_V2,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .setUserAuthenticationRequired(true);
        if (Build.VERSION.SDK_INT >= 30) {
            b.setUserAuthenticationParameters(
                    AUTH_VALIDITY_SECONDS,
                    KeyProperties.AUTH_BIOMETRIC_STRONG | KeyProperties.AUTH_DEVICE_CREDENTIAL);
        } else {
            b.setUserAuthenticationValidityDurationSeconds(AUTH_VALIDITY_SECONDS);
        }
        kg.init(b.build());
        return kg.generateKey();
    }

    private static SecretKey getOrCreateMemoryKey(String alias) throws Exception {
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
        if (secret == null || secret.trim().isEmpty()) throw new IllegalArgumentException("PROVIDER_SECRET_EMPTY");
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, getOrCreateProviderKey());
            byte[] encrypted = cipher.doFinal(secret.trim().getBytes(StandardCharsets.UTF_8));
            String encoded = PROVIDER_PREFIX +
                    Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP) + ":" +
                    Base64.encodeToString(encrypted, Base64.NO_WRAP);
            c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                    .putString(KEY_SECRET_V2, encoded)
                    .remove(KEY_SECRET_LEGACY)
                    .commit();
        } catch (Exception e) {
            throw new IllegalStateException("PROVIDER_SECRET_STORE_REQUIRES_RECENT_OWNER_AUTH", e);
        }
    }

    public static boolean hasProviderSecret(Context c) {
        String value = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_SECRET_V2, "");
        return value != null && value.startsWith(PROVIDER_PREFIX);
    }

    public static boolean hasLegacyProviderSecret(Context c) {
        SharedPreferences p = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String legacy = p.getString(KEY_SECRET_LEGACY, "");
        return legacy != null && !legacy.isEmpty();
    }

    public static String loadProviderSecret(Context c) {
        try {
            String encoded = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_SECRET_V2, "");
            if (encoded == null || !encoded.startsWith(PROVIDER_PREFIX)) return "";
            String[] parts = encoded.split(":", 4);
            if (parts.length != 4) return "";
            byte[] iv = Base64.decode(parts[2], Base64.NO_WRAP);
            byte[] encrypted = Base64.decode(parts[3], Base64.NO_WRAP);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, getOrCreateProviderKey(), new GCMParameterSpec(128, iv));
            return new String(cipher.doFinal(encrypted), StandardCharsets.UTF_8);
        } catch (Exception e) {
            throw new IllegalStateException("PROVIDER_SECRET_USE_REQUIRES_RECENT_OWNER_AUTH", e);
        }
    }

    public static void clearProviderSecret(Context c) {
        c.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .remove(KEY_SECRET_V2).remove(KEY_SECRET_LEGACY).commit();
    }

    static String encryptMemory(String plaintext) {
        try {
            if (plaintext == null) throw new IllegalArgumentException("MEMORY_NULL");
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, getOrCreateMemoryKey(MEMORY_ALIAS_V2));
            byte[] encrypted = cipher.doFinal(plaintext.getBytes(StandardCharsets.UTF_8));
            return MEMORY_PREFIX_V2 +
                    Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP) + ":" +
                    Base64.encodeToString(encrypted, Base64.NO_WRAP);
        } catch (Exception e) {
            throw new IllegalStateException("MEMORY_ENCRYPT_FAILED", e);
        }
    }

    static String decryptMemory(String encoded) {
        if (!isEncryptedMemoryBlob(encoded)) return null;
        try {
            boolean v2 = encoded.startsWith(MEMORY_PREFIX_V2);
            String[] parts = encoded.split(":", 4);
            byte[] iv = Base64.decode(parts[2], Base64.NO_WRAP);
            byte[] encrypted = Base64.decode(parts[3], Base64.NO_WRAP);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE,
                    getOrCreateMemoryKey(v2 ? MEMORY_ALIAS_V2 : MEMORY_ALIAS_V1),
                    new GCMParameterSpec(128, iv));
            return new String(cipher.doFinal(encrypted), StandardCharsets.UTF_8);
        } catch (Exception e) {
            return null;
        }
    }

    static boolean isEncryptedMemoryBlob(String value) {
        if (value == null) return false;
        if (!value.startsWith(MEMORY_PREFIX_V2) && !value.startsWith(MEMORY_PREFIX_V1)) return false;
        String[] parts = value.split(":", 4);
        return parts.length == 4 && !parts[2].isEmpty() && !parts[3].isEmpty();
    }
}
