package com.mehmetcerdik.ownerai;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;

/** Exact Owner/Device v1 wire format shared with the Python backend. No network access. */
public final class OmegaV1Envelope {
    private OmegaV1Envelope() {}

    public static final String PATH = "/api/v1/owner/chat";

    static String sha256Hex(byte[] value) throws Exception {
        byte[] hash = MessageDigest.getInstance("SHA-256").digest(value);
        StringBuilder sb = new StringBuilder(64);
        for (byte b : hash) sb.append(String.format(Locale.ROOT, "%02x", b & 0xff));
        return sb.toString();
    }

    public static byte[] canonical(byte[] body, String timestamp, String nonce,
                                   String ownerId, String deviceId) throws Exception {
        if (body == null || body.length == 0 || body.length > 65536) throw new SecurityException("OWNER_BODY_DENIED");
        if (timestamp == null || !timestamp.matches("[0-9]{10}")) throw new SecurityException("OWNER_TIMESTAMP_DENIED");
        if (nonce == null || !nonce.matches("[a-f0-9]{32,64}")) throw new SecurityException("OWNER_NONCE_DENIED");
        if (ownerId == null || !ownerId.matches("[A-Za-z0-9_-]{1,64}")
                || deviceId == null || !deviceId.matches("[a-f0-9]{64}")) {
            throw new SecurityException("OWNER_IDENTITY_DENIED");
        }
        return ("OMEGA-OWNER-API-V1\nPOST\n" + PATH + "\n" + sha256Hex(body) + "\n"
                + timestamp + "\n" + nonce + "\n" + ownerId + "\n" + deviceId)
                .getBytes(StandardCharsets.UTF_8);
    }
}
