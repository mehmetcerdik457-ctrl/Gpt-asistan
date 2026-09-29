package com.mehmetcerdik.ownerai;

import android.content.Context;
import android.os.SystemClock;

import java.util.UUID;

public final class OwnerSession {
    private static final long SESSION_MS = 2L * 60L * 1000L;
    private static final long FRESH_AUTH_MS = 30L * 1000L;

    private static volatile long authorizedUntilElapsedMs;
    private static volatile long freshUntilElapsedMs;
    private static volatile String deviceId = "";
    private static volatile long deviceCounter;
    private static volatile String sessionId = "";
    private static volatile boolean debugOnly;

    private OwnerSession() {}

    public static synchronized void authorize(Context c) {
        TrustedDeviceManager.Proof proof = TrustedDeviceManager.provePossession(c, true);
        long now = SystemClock.elapsedRealtime();
        authorizedUntilElapsedMs = now + SESSION_MS;
        freshUntilElapsedMs = now + FRESH_AUTH_MS;
        deviceId = proof.deviceId;
        deviceCounter = proof.counter;
        sessionId = UUID.randomUUID().toString();
        debugOnly = false;
    }

    static synchronized void authorizeDebug() {
        long now = SystemClock.elapsedRealtime();
        authorizedUntilElapsedMs = now + SESSION_MS;
        freshUntilElapsedMs = now + FRESH_AUTH_MS;
        deviceId = "DEBUG_EMULATOR_ONLY";
        deviceCounter++;
        sessionId = "DEBUG-" + UUID.randomUUID();
        debugOnly = true;
    }

    public static boolean isAuthorized(Context c) {
        if (SystemClock.elapsedRealtime() >= authorizedUntilElapsedMs) return false;
        if (sessionId.isEmpty() || deviceId.isEmpty()) return false;
        if (debugOnly) return com.example.gptasistan.BuildConfig.DEBUG;
        return TrustedDeviceManager.isRegisteredAndActive(c) && deviceId.equals(TrustedDeviceManager.deviceId());
    }

    public static boolean isFresh(Context c) {
        return isAuthorized(c) && SystemClock.elapsedRealtime() < freshUntilElapsedMs;
    }

    public static synchronized void clear() {
        authorizedUntilElapsedMs = 0L;
        freshUntilElapsedMs = 0L;
        deviceId = "";
        deviceCounter = 0L;
        sessionId = "";
        debugOnly = false;
    }

    public static long remainingMs() {
        return Math.max(0L, authorizedUntilElapsedMs - SystemClock.elapsedRealtime());
    }

    public static String classification() {
        return debugOnly ? "DEBUG_ONLY_SESSION" : "DEVICE_BOUND_LOCAL_SECURE_SESSION";
    }

    public static String deviceIdForStatus() { return deviceId; }
    public static long deviceCounterForStatus() { return deviceCounter; }
}
