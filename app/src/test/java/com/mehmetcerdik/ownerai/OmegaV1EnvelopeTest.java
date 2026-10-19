package com.mehmetcerdik.ownerai;

import static org.junit.Assert.*;
import org.junit.Test;
import java.nio.charset.StandardCharsets;

public final class OmegaV1EnvelopeTest {
    private static final String NONCE = "0123456789abcdef0123456789abcdef";
    private static final String DEVICE = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

    @Test public void exactBackendContractCanonical() throws Exception {
        byte[] raw = "{}".getBytes(StandardCharsets.UTF_8);
        String actual = new String(OmegaV1Envelope.canonical(raw, "1792440000", NONCE, "owner-test", DEVICE),
                StandardCharsets.UTF_8);
        assertEquals("OMEGA-OWNER-API-V1\nPOST\n/api/v1/owner/chat\n"
                + "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a\n"
                + "1792440000\n" + NONCE + "\nowner-test\n" + DEVICE, actual);
    }

    @Test public void mutatedPayloadChangesSignedMessage() throws Exception {
        String one = new String(OmegaV1Envelope.canonical("{\"a\":1}".getBytes(StandardCharsets.UTF_8),
                "1792440000", NONCE, "owner-test", DEVICE), StandardCharsets.UTF_8);
        String two = new String(OmegaV1Envelope.canonical("{\"a\":2}".getBytes(StandardCharsets.UTF_8),
                "1792440000", NONCE, "owner-test", DEVICE), StandardCharsets.UTF_8);
        assertNotEquals(one, two);
    }

    @Test public void malformedIdsAndNoncesDenied() throws Exception {
        try {
            OmegaV1Envelope.canonical(new byte[]{'x'}, "1792440000", "not-hex", "owner-test", DEVICE);
            fail("invalid nonce accepted");
        } catch (SecurityException expected) {}
        try {
            OmegaV1Envelope.canonical(new byte[]{'x'}, "1792440000", NONCE, "owner\nadmin", DEVICE);
            fail("newlines in owner id accepted");
        } catch (SecurityException expected) {}
    }
}
