package com.mehmetcerdik.ownerai;

public final class OwnerSession {
    private static final long SESSION_MS = 5L * 60L * 1000L;
    private static volatile long authorizedUntilElapsedMs = 0L;

    private OwnerSession() {}

    public static boolean isAuthorized() {
        return android.os.SystemClock.elapsedRealtime() < authorizedUntilElapsedMs;
    }

    static void authorize() {
        authorizedUntilElapsedMs = android.os.SystemClock.elapsedRealtime() + SESSION_MS;
    }

    public static void clear() {
        authorizedUntilElapsedMs = 0L;
    }

    public static long remainingMs() {
        return Math.max(0L, authorizedUntilElapsedMs - android.os.SystemClock.elapsedRealtime());
    }
}
