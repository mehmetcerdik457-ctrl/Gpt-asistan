package com.mehmetcerdik.ownerai;

import android.content.Context;
import android.os.Build;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

/** Signs only an explicitly authorized request. Never stores provider secrets in headers. */
public final class OwnerOmegaV1Signer {
    private static final String OWNER_ALIAS = "mehmet_owner_omega_request_v1";
    private static final String KEYSTORE = "AndroidKeyStore";
    private static final SecureRandom RNG = new SecureRandom();

    private OwnerOmegaV1Signer() {}

    private static KeyPair ownerKey() throws Exception {
        KeyStore ks = KeyStore.getInstance(KEYSTORE);
        ks.load(null);
        if (ks.containsAlias(OWNER_ALIAS)) {
            return new KeyPair(ks.getCertificate(OWNER_ALIAS).getPublicKey(),
                    (java.security.PrivateKey) ks.getKey(OWNER_ALIAS, null));
        }
        KeyPairGenerator gen = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, KEYSTORE);
        KeyGenParameterSpec.Builder b = new KeyGenParameterSpec.Builder(
                OWNER_ALIAS, KeyProperties.PURPOSE_SIGN | KeyProperties.PURPOSE_VERIFY)
                .setAlgorithmParameterSpec(new ECGenParameterSpec("secp256r1"))
                .setDigests(KeyProperties.DIGEST_SHA256)
                .setUserAuthenticationRequired(true);
        if (Build.VERSION.SDK_INT >= 30) {
            b.setUserAuthenticationParameters(30,
                    KeyProperties.AUTH_BIOMETRIC_STRONG | KeyProperties.AUTH_DEVICE_CREDENTIAL);
        } else {
            b.setUserAuthenticationValidityDurationSeconds(30);
        }
        if (Build.VERSION.SDK_INT >= 28) b.setUnlockedDeviceRequired(true);
        gen.initialize(b.build());
        return gen.generateKeyPair();
    }

    public static String ownerPublicDerBase64(Context c) {
        if (!OwnerSession.isFresh(c)) throw new SecurityException("FRESH_OWNER_AUTH_REQUIRED");
        try {
            return Base64.encodeToString(ownerKey().getPublic().getEncoded(),
                    Base64.URL_SAFE | Base64.NO_PADDING | Base64.NO_WRAP);
        } catch (Exception e) {
            throw new SecurityException("OWNER_PUBLIC_EXPORT_DENIED", e);
        }
    }

    public static Map<String, String> signedHeaders(Context c, byte[] exactJson,
                                                     String approvedOwnerId) {
        if (!OwnerSession.isFresh(c)) throw new SecurityException("FRESH_OWNER_AUTH_REQUIRED");
        if (!TrustedDeviceManager.isRegisteredAndActive(c)) throw new SecurityException("DEVICE_NOT_REGISTERED");
        try {
            String deviceId = TrustedDeviceManager.deviceId();
            String timestamp = Long.toString(System.currentTimeMillis() / 1000L);
            byte[] random = new byte[24];
            RNG.nextBytes(random);
            StringBuilder n = new StringBuilder(48);
            for (byte b : random) n.append(String.format(Locale.ROOT, "%02x", b & 0xff));
            String nonce = n.toString();
            byte[] message = OmegaV1Envelope.canonical(exactJson, timestamp, nonce, approvedOwnerId, deviceId);
            Signature sig = Signature.getInstance("SHA256withECDSA");
            sig.initSign(ownerKey().getPrivate());
            sig.update(message);
            byte[] ownerProof = sig.sign();
            byte[] deviceProof = TrustedDeviceManager.signOmegaV1(c, message);
            Map<String, String> h = new LinkedHashMap<>();
            h.put("X-Omega-Owner-Id", approvedOwnerId);
            h.put("X-Omega-Device-Id", deviceId);
            h.put("X-Omega-Timestamp", timestamp);
            h.put("X-Omega-Nonce", nonce);
            h.put("X-Omega-Owner-Proof", Base64.encodeToString(ownerProof,
                    Base64.URL_SAFE | Base64.NO_PADDING | Base64.NO_WRAP));
            h.put("X-Omega-Device-Proof", Base64.encodeToString(deviceProof,
                    Base64.URL_SAFE | Base64.NO_PADDING | Base64.NO_WRAP));
            return h;
        } catch (SecurityException e) {
            throw e;
        } catch (Exception e) {
            // Never echo Keystore exception strings (they may contain environment details).
            throw new SecurityException("OWNER_V1_SIGNATURE_UNAVAILABLE");
        }
    }
}
