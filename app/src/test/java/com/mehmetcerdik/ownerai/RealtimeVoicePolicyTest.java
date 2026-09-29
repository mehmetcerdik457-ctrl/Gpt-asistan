package com.mehmetcerdik.ownerai;

import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;

public final class RealtimeVoicePolicyTest {
    @Test public void gaWebRtcEndpointsAndCredentialBoundaryArePinned() {
        assertEquals("/v1/realtime/client_secrets", RealtimeVoicePolicy.CLIENT_SECRET_PATH);
        assertEquals("/v1/realtime/calls", RealtimeVoicePolicy.WEBRTC_CALLS_PATH);
        JSONObject status = RealtimeVoicePolicy.status();
        assertEquals("TRUSTED_EPHEMERAL_TOKEN_ISSUER_REQUIRED_NOT_RUNTIME_VERIFIED", status.optString("status"));
        assertFalse(status.optBoolean("long_lived_provider_secret_in_realtime_client", true));
        assertTrue(status.optBoolean("microphone_requires_explicit_owner_intent_and_os_permission", false));
    }

    @Test public void malformedEphemeralTokensAreDenied() {
        assertFalse(RealtimeVoicePolicy.acceptEphemeralToken(null));
        assertFalse(RealtimeVoicePolicy.acceptEphemeralToken("short"));
        assertFalse(RealtimeVoicePolicy.acceptEphemeralToken("12345678901234567890\n"));
        assertTrue(RealtimeVoicePolicy.acceptEphemeralToken("12345678901234567890"));
    }
}
