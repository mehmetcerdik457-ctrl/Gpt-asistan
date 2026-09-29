package com.mehmetcerdik.ownerai;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyInfo;
import android.security.keystore.KeyProperties;
import android.security.keystore.StrongBoxUnavailableException;
import android.util.Base64;

import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;
import java.util.Locale;

public final class TrustedDeviceManager {
    private static final String KEYSTORE = "AndroidKeyStore";
    private static final String DEVICE_ALIAS = "mehmet_owner_device_identity_v1";
    private static final String PREFS = "owner_trusted_device_v1";
    private static final long PROOF_MAX_AGE_MS = 30_000L;
    private static final int DEVICE_KEY_AUTH_VALIDITY_SECONDS = 30;
    private static final SecureRandom RNG = new SecureRandom();

    public static final class Proof {
        public final String deviceId;
        public final long counter;
        public final long timestampMs;
        public final String nonceHash;
        public final boolean hardwareBacked;

        Proof(String deviceId, long counter, long timestampMs, String nonceHash, boolean hardwareBacked) {
            this.deviceId = deviceId;
            this.counter = counter;
            this.timestampMs = timestampMs;
            this.nonceHash = nonceHash;
            this.hardwareBacked = hardwareBacked;
        }
    }

    private TrustedDeviceManager() {}

    private static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private static KeyPair ensureKeyPair() throws Exception {
        KeyStore ks = KeyStore.getInstance(KEYSTORE);
        ks.load(null);
        if (ks.containsAlias(DEVICE_ALIAS)) {
            PrivateKey priv = (PrivateKey) ks.getKey(DEVICE_ALIAS, null);
            PublicKey pub = ks.getCertificate(DEVICE_ALIAS).getPublicKey();
            return new KeyPair(pub, priv);
        }
        try {
            return generate(Build.VERSION.SDK_INT >= 28);
        } catch (StrongBoxUnavailableException e) {
            return generate(false);
        }
    }

    private static KeyPair generate(boolean strongBox) throws Exception {
        KeyPairGenerator gen = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, KEYSTORE);
        KeyGenParameterSpec.Builder b = new KeyGenParameterSpec.Builder(
                DEVICE_ALIAS, KeyProperties.PURPOSE_SIGN | KeyProperties.PURPOSE_VERIFY)
                .setAlgorithmParameterSpec(new ECGenParameterSpec("secp256r1"))
                .setDigests(KeyProperties.DIGEST_SHA256)
                .setUserAuthenticationRequired(true);
        if (Build.VERSION.SDK_INT >= 30) {
            b.setUserAuthenticationParameters(
                    DEVICE_KEY_AUTH_VALIDITY_SECONDS,
                    KeyProperties.AUTH_BIOMETRIC_STRONG | KeyProperties.AUTH_DEVICE_CREDENTIAL);
        } else {
            b.setUserAuthenticationValidityDurationSeconds(DEVICE_KEY_AUTH_VALIDITY_SECONDS);
        }
        if (Build.VERSION.SDK_INT >= 28) {
            b.setUnlockedDeviceRequired(true);
            if (strongBox) b.setIsStrongBoxBacked(true);
        }
        gen.initialize(b.build());
        return gen.generateKeyPair();
    }

    public static boolean isHardwareBacked() {
        try {
            KeyPair kp = ensureKeyPair();
            KeyFactory f = KeyFactory.getInstance(kp.getPrivate().getAlgorithm(), KEYSTORE);
            KeyInfo info = f.getKeySpec(kp.getPrivate(), KeyInfo.class);
            return info.isInsideSecureHardware();
        } catch (Exception e) {
            return false;
        }
    }

    public static String deviceId() {
        try {
            return sha256(ensureKeyPair().getPublic().getEncoded());
        } catch (Exception e) {
            return "";
        }
    }

    public static boolean isRegisteredAndActive(Context c) {
        SharedPreferences p = prefs(c);
        String registered = p.getString("registered_device_id", "");
        return !p.getBoolean("revoked", false) && !registered.isEmpty() && registered.equals(deviceId());
    }

    public static void revoke(Context c) {
        prefs(c).edit().putBoolean("revoked", true).commit();
    }

    public static Proof provePossession(Context c, boolean requireHardwareBacked) {
        try {
            KeyPair kp = ensureKeyPair();
            boolean hardware = isHardwareBacked();
            if (requireHardwareBacked && !hardware) throw new SecurityException("DEVICE_KEY_NOT_HARDWARE_BACKED");
            String deviceId = sha256(kp.getPublic().getEncoded());
            SharedPreferences p = prefs(c);
            if (p.getBoolean("revoked", false)) throw new SecurityException("DEVICE_REVOKED");
            String registered = p.getString("registered_device_id", "");
            if (registered == null || registered.isEmpty()) {
                if (!p.edit().putString("registered_device_id", deviceId).commit()) {
                    throw new SecurityException("DEVICE_REGISTRATION_FAILED");
                }
                registered = deviceId;
            }
            if (!deviceId.equals(registered)) throw new SecurityException("DEVICE_IDENTITY_MISMATCH");

            long previousCounter = p.getLong("counter", 0L);
            if (previousCounter == Long.MAX_VALUE) throw new SecurityException("DEVICE_COUNTER_EXHAUSTED");
            long counter = previousCounter + 1L;
            long timestamp = System.currentTimeMillis();
            byte[] nonce = new byte[32];
            RNG.nextBytes(nonce);
            String nonceB64 = Base64.encodeToString(nonce, Base64.NO_WRAP);
            String payload = deviceId + "|" + counter + "|" + timestamp + "|" + nonceB64;

            Signature signer = Signature.getInstance("SHA256withECDSA");
            signer.initSign(kp.getPrivate());
            signer.update(payload.getBytes(StandardCharsets.UTF_8));
            byte[] signature = signer.sign();

            Signature verifier = Signature.getInstance("SHA256withECDSA");
            verifier.initVerify(kp.getPublic());
            verifier.update(payload.getBytes(StandardCharsets.UTF_8));
            if (!verifier.verify(signature)) throw new SecurityException("DEVICE_POSSESSION_PROOF_INVALID");
            if (Math.abs(System.currentTimeMillis() - timestamp) > PROOF_MAX_AGE_MS) {
                throw new SecurityException("DEVICE_PROOF_STALE");
            }

            String nonceHash = sha256(nonce);
            long lastVerified = p.getLong("last_verified_counter", 0L);
            String lastNonceHash = p.getString("last_nonce_hash", "");
            if (counter <= lastVerified || nonceHash.equals(lastNonceHash)) {
                throw new SecurityException("DEVICE_PROOF_REPLAY");
            }
            if (!p.edit()
                    .putLong("counter", counter)
                    .putLong("last_verified_counter", counter)
                    .putString("last_nonce_hash", nonceHash)
                    .commit()) {
                throw new SecurityException("DEVICE_PROOF_STATE_COMMIT_FAILED");
            }
            return new Proof(deviceId, counter, timestamp, nonceHash, hardware);
        } catch (SecurityException e) {
            throw e;
        } catch (Exception e) {
            throw new SecurityException("TRUSTED_DEVICE_PROOF_FAILED", e);
        }
    }

    private static String sha256(byte[] data) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(data);
        StringBuilder out = new StringBuilder();
        for (byte b : digest) out.append(String.format(Locale.ROOT, "%02x", b & 0xff));
        return out.toString();
    }
}
