package com.mehmetcerdik.ownerai;

import org.junit.Test;

import static org.junit.Assert.fail;

public final class TrustedDevicePolicyTest {
    private static void expectSecurity(String expected, Runnable r) {
        try {
            r.run();
            fail("Expected SecurityException: " + expected);
        } catch (SecurityException e) {
            if (!expected.equals(e.getMessage())) {
                fail("Expected " + expected + " but was " + e.getMessage());
            }
        }
    }

    @Test public void freshMonotonicUniqueProofIsAccepted() {
        long now = 1_000_000L;
        TrustedDeviceManager.validateFreshAndNotReplay(
                now - 1_000L, now, 11L, 10L, "nonce-new", "nonce-old");
    }

    @Test public void staleAndFarFutureProofsAreDenied() {
        long now = 1_000_000L;
        expectSecurity("DEVICE_PROOF_STALE", () ->
                TrustedDeviceManager.validateFreshAndNotReplay(
                        now - 30_001L, now, 11L, 10L, "nonce-new", "nonce-old"));
        expectSecurity("DEVICE_PROOF_STALE", () ->
                TrustedDeviceManager.validateFreshAndNotReplay(
                        now + 5_001L, now, 11L, 10L, "nonce-new", "nonce-old"));
    }

    @Test public void counterReplayAndNonceReplayAreDenied() {
        long now = 1_000_000L;
        expectSecurity("DEVICE_PROOF_REPLAY", () ->
                TrustedDeviceManager.validateFreshAndNotReplay(
                        now, now, 10L, 10L, "nonce-new", "nonce-old"));
        expectSecurity("DEVICE_PROOF_REPLAY", () ->
                TrustedDeviceManager.validateFreshAndNotReplay(
                        now, now, 11L, 10L, "same", "same"));
    }

    @Test public void emptyNonceFailsClosed() {
        long now = 1_000_000L;
        expectSecurity("DEVICE_PROOF_REPLAY", () ->
                TrustedDeviceManager.validateFreshAndNotReplay(
                        now, now, 11L, 10L, "", "nonce-old"));
    }
}
