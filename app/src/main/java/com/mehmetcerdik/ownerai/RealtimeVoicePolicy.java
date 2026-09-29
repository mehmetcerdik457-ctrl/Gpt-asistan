package com.mehmetcerdik.ownerai;

import org.json.JSONObject;

public final class RealtimeVoicePolicy {
    public static final String TRANSPORT = "WEBRTC";
    public static final String API_HOST = "api.openai.com";
    public static final String CLIENT_SECRET_PATH = "/v1/realtime/client_secrets";
    public static final String WEBRTC_CALLS_PATH = "/v1/realtime/calls";
    public static final String MODEL = "gpt-realtime-2.1";
    public static final String CREDENTIAL_POLICY = "SHORT_LIVED_EPHEMERAL_TOKEN_FROM_TRUSTED_ISSUER";

    private RealtimeVoicePolicy() {}

    public static JSONObject status() {
        JSONObject o = new JSONObject();
        try {
            o.put("status", "TRUSTED_EPHEMERAL_TOKEN_ISSUER_REQUIRED_NOT_RUNTIME_VERIFIED");
            o.put("transport", TRANSPORT);
            o.put("host", API_HOST);
            o.put("client_secret_path", CLIENT_SECRET_PATH);
            o.put("webrtc_calls_path", WEBRTC_CALLS_PATH);
            o.put("model", MODEL);
            o.put("credential_policy", CREDENTIAL_POLICY);
            o.put("long_lived_provider_secret_in_realtime_client", false);
            o.put("microphone_requires_explicit_owner_intent_and_os_permission", true);
            o.put("runtime_gate", "TRUSTED_EPHEMERAL_TOKEN_ISSUER_REQUIRED");
        } catch (Exception ignored) {}
        return o;
    }

    public static boolean acceptEphemeralToken(String token) {
        if (token == null || token.contains("\n") || token.contains("\r")) return false;
        String t = token.trim();
        return t.length() >= 20 && t.length() <= 4096;
    }
}
