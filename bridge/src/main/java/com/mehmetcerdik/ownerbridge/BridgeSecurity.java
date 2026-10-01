package com.mehmetcerdik.ownerbridge;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.content.pm.SigningInfo;
import android.os.Build;
import android.os.Process;
import android.os.SystemClock;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.UUID;

final class BridgeSecurity {
    static final String CORE_PACKAGE = "com.mehmetcerdik.ownerai";
    static final String CORE_SIGNER = BuildConfig.EXPECTED_CORE_SIGNER_SHA256;
    static final String WORKER_PACKAGE = "com.codespaceapps.aichat";
    static final String WORKER_SIGNER = "7b4a4b483ad4fdfa7bcab3c4ba9fd5a0461cab208fc7120a4d8d2f4901b3a097";
    static final long MAX_ARM_MS = 2 * 60 * 1000L;
    static final long DEFAULT_ARM_MS = 60 * 1000L;

    private static final String PREFS = "mehmet_owner_bridge_state_v50";
    private static final String KEY_UNTIL = "armed_until_elapsed";
    private static final String KEY_SESSION = "armed_session";
    private static final String KEY_PID = "armed_pid";
    private static final String KEY_EMERGENCY = "emergency_stop";
    private static final String SESSION = UUID.randomUUID().toString();

    private BridgeSecurity() {}

    static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static void ensureDefaults(Context c) {
        SharedPreferences p = prefs(c);
        if (!p.contains(KEY_EMERGENCY)) {
            p.edit().putBoolean(KEY_EMERGENCY, true).putLong(KEY_UNTIL, 0)
                    .putString(KEY_SESSION, "").putInt(KEY_PID, -1).commit();
        }
    }

    static String getSigner(Context c, String pkg) {
        try {
            PackageManager pm = c.getPackageManager();
            Signature[] sigs;
            if (Build.VERSION.SDK_INT >= 28) {
                PackageInfo pi = pm.getPackageInfo(pkg, PackageManager.GET_SIGNING_CERTIFICATES);
                SigningInfo si = pi.signingInfo;
                if (si == null) return null;
                sigs = si.getApkContentsSigners();
            } else {
                @SuppressWarnings("deprecation") PackageInfo pi = pm.getPackageInfo(pkg, PackageManager.GET_SIGNATURES);
                @SuppressWarnings("deprecation") Signature[] legacy = pi.signatures;
                sigs = legacy;
            }
            if (sigs == null || sigs.length != 1) return null;
            return sha256Bytes(sigs[0].toByteArray());
        } catch (Throwable t) { return null; }
    }

    static boolean verifyCore(Context c) {
        String signer = getSigner(c, CORE_PACKAGE);
        return signer != null && CORE_SIGNER.equalsIgnoreCase(signer);
    }

    static boolean isEmergencyStopped(Context c) {
        return prefs(c).getBoolean(KEY_EMERGENCY, true);
    }

    static boolean isArmed(Context c) {
        SharedPreferences p = prefs(c);
        return !p.getBoolean(KEY_EMERGENCY, true)
                && SESSION.equals(p.getString(KEY_SESSION, ""))
                && Process.myPid() == p.getInt(KEY_PID, -1)
                && p.getLong(KEY_UNTIL, 0) > 0
                && SystemClock.elapsedRealtime() <= p.getLong(KEY_UNTIL, 0);
    }

    static long arm(Context c, long requested) {
        long ttl = requested <= 0 ? DEFAULT_ARM_MS : Math.min(requested, MAX_ARM_MS);
        long until = SystemClock.elapsedRealtime() + ttl;
        prefs(c).edit().putBoolean(KEY_EMERGENCY, false).putLong(KEY_UNTIL, until)
                .putString(KEY_SESSION, SESSION).putInt(KEY_PID, Process.myPid()).commit();
        BridgeEvidenceStore.record(c, "ARM", "PASS", "ttl=" + ttl);
        return until;
    }

    static void stop(Context c) {
        prefs(c).edit().putBoolean(KEY_EMERGENCY, true).putLong(KEY_UNTIL, 0)
                .putString(KEY_SESSION, "").putInt(KEY_PID, -1).commit();
        BridgeEvidenceStore.record(c, "EMERGENCY_STOP", "PASS", "");
    }

    static String approveInstalledPackage(Context c, String pkg) {
        if (!isFixedApprovedPackage(pkg)) return null;
        String signer = getSigner(c, pkg);
        if (signer == null) return null;
        String expected = CORE_PACKAGE.equals(pkg) ? CORE_SIGNER : WORKER_SIGNER;
        if (!expected.equalsIgnoreCase(signer)) return null;
        BridgeEvidenceStore.record(c, "VERIFY_FIXED_PACKAGE", "PASS", pkg + "|" + signer);
        return signer;
    }

    static boolean revokePackage(Context c, String pkg) { return false; }

    static boolean isPackageApproved(Context c, String pkg) {
        if (!isFixedApprovedPackage(pkg)) return false;
        String signer = getSigner(c, pkg);
        if (signer == null) return false;
        return (CORE_PACKAGE.equals(pkg) ? CORE_SIGNER : WORKER_SIGNER).equalsIgnoreCase(signer);
    }

    static boolean isFixedApprovedPackage(String pkg) {
        return CORE_PACKAGE.equals(pkg) || WORKER_PACKAGE.equals(pkg);
    }

    static boolean validPackageName(String p) {
        return p != null && p.length() >= 3 && p.length() <= 255
                && p.matches("[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z0-9_]+)+");
    }

    static String sha256String(String s) {
        return sha256Bytes((s == null ? "" : s).getBytes(StandardCharsets.UTF_8));
    }

    static String sha256Bytes(byte[] data) {
        try {
            byte[] out = MessageDigest.getInstance("SHA-256").digest(data);
            StringBuilder b = new StringBuilder();
            for (byte x : out) b.append(String.format(Locale.ROOT, "%02x", x & 255));
            return b.toString();
        } catch (Throwable t) { return "HASH_ERROR"; }
    }
}
