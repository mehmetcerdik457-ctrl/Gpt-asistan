package com.mehmetcerdik.ownerbridge;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.content.pm.ResolveInfo;
import android.content.pm.SigningInfo;
import android.os.Build;
import android.os.Process;
import android.os.SystemClock;
import android.provider.Settings;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;

final class BridgeSecurity {
    static final String CORE_PACKAGE = "com.mehmetcerdik.ownerai";
    static final String CORE_SIGNER = "279084a36b7c17a1663bfba5fe1c5bdac974f8ef4ce56b21000d882493e39448";
    static final String WORKER_PACKAGE = "com.codespaceapps.aichat";
    static final String WORKER_SIGNER = "7b4a4b483ad4fdfa7bcab3c4ba9fd5a0461cab208fc7120a4d8d2f4901b3a097";
    static final long MAX_ARM_MS = 10 * 60 * 1000L;
    static final long DEFAULT_ARM_MS = 5 * 60 * 1000L;
    static final String SESSION_CLASS = "DEVICE_CREDENTIAL_GATED_SIGNED_CORE_SESSION";

    private static final String PREFS = "mehm_owner_bridge_state";
    private static final String KEY_APPROVED = "approved_package_signers";
    private static final String KEY_EMERGENCY = "emergency_stop";
    private static final String KEY_AUDIT_SEQ = "audit_seq";
    private static final String KEY_AUDIT_HEAD = "audit_head_hash";
    private static final String KEY_AUDIT_SEGMENT = "audit_segment";
    private static final String KEY_AUDIT_COUNT = "audit_count";
    private static final String KEY_CUR_START_SEQ = "audit_cur_start_seq";
    private static final String KEY_CUR_START_PREV = "audit_cur_start_prev";
    private static final String KEY_PREV_START_SEQ = "audit_prev_start_seq";
    private static final String KEY_PREV_START_PREV = "audit_prev_start_prev";
    private static final int AUDIT_MAX_RECORDS_PER_SEGMENT = 500;
    private static final String AUDIT_CURRENT = "owner_audit_current.log";
    private static final String AUDIT_PREVIOUS = "owner_audit_previous.log";
    private static final String PROCESS_SESSION_ID = UUID.randomUUID().toString();

    private static volatile long armedUntilElapsed = 0L;
    private static volatile int armedPid = -1;
    private static volatile int armedBootCount = Integer.MIN_VALUE;
    private static volatile String armedSession = "";

    private BridgeSecurity() {}

    static SharedPreferences prefs(Context c) { return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE); }

    static synchronized void ensureDefaults(Context c) {
        SharedPreferences p = prefs(c);
        Set<String> current = p.getStringSet(KEY_APPROVED, null);
        SharedPreferences.Editor e = p.edit();
        if (current == null) {
            HashSet<String> s = new HashSet<>();
            s.add(WORKER_PACKAGE + "|" + WORKER_SIGNER);
            e.putStringSet(KEY_APPROVED, s);
        } else if (!current.contains(WORKER_PACKAGE + "|" + WORKER_SIGNER)) {
            HashSet<String> s = new HashSet<>(current);
            s.removeIf(v -> v.startsWith(WORKER_PACKAGE + "|"));
            s.add(WORKER_PACKAGE + "|" + WORKER_SIGNER);
            e.putStringSet(KEY_APPROVED, s);
        }
        if (!p.contains(KEY_EMERGENCY)) e.putBoolean(KEY_EMERGENCY, true);
        if (!p.contains(KEY_AUDIT_HEAD)) e.putString(KEY_AUDIT_HEAD, AuditChain.GENESIS);
        if (!p.contains(KEY_AUDIT_SEGMENT)) e.putLong(KEY_AUDIT_SEGMENT, 0L);
        if (!p.contains(KEY_CUR_START_SEQ)) e.putLong(KEY_CUR_START_SEQ, 1L);
        if (!p.contains(KEY_CUR_START_PREV)) e.putString(KEY_CUR_START_PREV, AuditChain.GENESIS);
        e.commit();
    }

    static synchronized void forceFailClosed(Context c, String reason) {
        armedUntilElapsed = 0L;
        armedPid = -1;
        armedBootCount = Integer.MIN_VALUE;
        armedSession = "";
        prefs(c).edit().putBoolean(KEY_EMERGENCY, true).commit();
        audit(c, "FAIL_CLOSED", "CONFIRMED", "", reason == null ? "" : reason);
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
        String s = getSigner(c, CORE_PACKAGE);
        return s != null && CORE_SIGNER.equalsIgnoreCase(s);
    }

    static int bootCount(Context c) {
        try { return Settings.Global.getInt(c.getContentResolver(), Settings.Global.BOOT_COUNT); }
        catch (Throwable t) { return Integer.MIN_VALUE; }
    }

    static boolean isArmed(Context c) {
        if (prefs(c).getBoolean(KEY_EMERGENCY, true)) return false;
        if (armedPid != Process.myPid()) return false;
        if (!PROCESS_SESSION_ID.equals(armedSession)) return false;
        if (armedBootCount != bootCount(c)) return false;
        long now = SystemClock.elapsedRealtime();
        return armedUntilElapsed > now && (armedUntilElapsed - now) <= MAX_ARM_MS;
    }

    static long armedRemainingMs(Context c) {
        if (!isArmed(c)) return 0L;
        return Math.max(0L, armedUntilElapsed - SystemClock.elapsedRealtime());
    }

    static synchronized long arm(Context c, long requestedMs) {
        long ttl = requestedMs <= 0 ? DEFAULT_ARM_MS : Math.min(requestedMs, MAX_ARM_MS);
        int boot = bootCount(c);
        long now = SystemClock.elapsedRealtime();
        armedPid = Process.myPid();
        armedBootCount = boot;
        armedSession = PROCESS_SESSION_ID;
        armedUntilElapsed = now + ttl;
        prefs(c).edit().putBoolean(KEY_EMERGENCY, false).commit();
        audit(c, "ARM", "TARGET_POSTCONDITION_CONFIRMED", "ttl_ms=" + ttl, "");
        return ttl;
    }

    static synchronized void stop(Context c) {
        armedUntilElapsed = 0L;
        armedPid = -1;
        armedBootCount = Integer.MIN_VALUE;
        armedSession = "";
        prefs(c).edit().putBoolean(KEY_EMERGENCY, true).commit();
        audit(c, "EMERGENCY_STOP", "TARGET_POSTCONDITION_CONFIRMED", "", "");
    }

    static boolean isEmergencyStopped(Context c) { return prefs(c).getBoolean(KEY_EMERGENCY, true); }

    static PackageDescriptor inspectInstalledPackage(Context c, String pkg) {
        if (!validPackageName(pkg)) return null;
        try {
            PackageManager pm = c.getPackageManager();
            ApplicationInfo ai = pm.getApplicationInfo(pkg, 0);
            String signer = getSigner(c, pkg);
            if (signer == null) return null;
            CharSequence label = pm.getApplicationLabel(ai);
            boolean launchable = pm.getLaunchIntentForPackage(pkg) != null;
            return new PackageDescriptor(pkg, label == null ? pkg : label.toString(), signer, launchable);
        } catch (Throwable t) { return null; }
    }

    static List<PackageDescriptor> listLaunchablePackages(Context c) {
        ArrayList<PackageDescriptor> out = new ArrayList<>();
        HashSet<String> seen = new HashSet<>();
        try {
            Intent launcher = new Intent(Intent.ACTION_MAIN); launcher.addCategory(Intent.CATEGORY_LAUNCHER);
            for (ResolveInfo ri : c.getPackageManager().queryIntentActivities(launcher, 0)) {
                if (ri == null || ri.activityInfo == null || ri.activityInfo.packageName == null) continue;
                String pkg = ri.activityInfo.packageName;
                if (!seen.add(pkg) || CORE_PACKAGE.equals(pkg) || "com.mehmetcerdik.ownerbridge".equals(pkg)) continue;
                PackageDescriptor d = inspectInstalledPackage(c, pkg);
                if (d != null && d.launchable) out.add(d);
            }
        } catch (Throwable ignored) {}
        Collections.sort(out, (a,b) -> (a.label + a.packageName).compareToIgnoreCase(b.label + b.packageName));
        return out;
    }

    static synchronized String approveInstalledPackage(Context c, String pkg) {
        if (CORE_PACKAGE.equals(pkg) || "com.mehmetcerdik.ownerbridge".equals(pkg)) return null;
        PackageDescriptor d = inspectInstalledPackage(c, pkg);
        if (d == null || !d.launchable) return null;
        HashSet<String> set = new HashSet<>(prefs(c).getStringSet(KEY_APPROVED, new HashSet<>()));
        set.removeIf(v -> v.startsWith(pkg + "|"));
        set.add(pkg + "|" + d.signer.toLowerCase(Locale.ROOT));
        boolean committed = prefs(c).edit().putStringSet(KEY_APPROVED, set).commit();
        if (!committed || !isPackageApproved(c, pkg)) { hardStopWithoutAudit(c); return null; }
        if (!audit(c, "APPROVE_PACKAGE", "TARGET_POSTCONDITION_CONFIRMED", pkg + "|" + d.signer, "")) return null;
        return d.signer;
    }

    static boolean isPackageApproved(Context c, String pkg) {
        if (!validPackageName(pkg)) return false;
        String signer = getSigner(c, pkg);
        if (signer == null) return false;
        Set<String> set = prefs(c).getStringSet(KEY_APPROVED, new HashSet<>());
        return set.contains(pkg + "|" + signer.toLowerCase(Locale.ROOT));
    }

    static synchronized boolean revokePackage(Context c, String pkg) {
        if (!validPackageName(pkg) || WORKER_PACKAGE.equals(pkg)) return false;
        HashSet<String> set = new HashSet<>(prefs(c).getStringSet(KEY_APPROVED, new HashSet<>()));
        boolean changed = set.removeIf(v -> v.startsWith(pkg + "|"));
        if (changed) {
            boolean committed = prefs(c).edit().putStringSet(KEY_APPROVED, set).commit();
            if (!committed || isPackageApproved(c, pkg)) { hardStopWithoutAudit(c); return false; }
        }
        if (!audit(c, "REVOKE_PACKAGE", changed ? "TARGET_POSTCONDITION_CONFIRMED" : "OBSERVED", pkg, changed ? "" : "NOT_APPROVED")) return false;
        return changed;
    }

    static synchronized int revokeAllNonDefaultPackages(Context c) {
        HashSet<String> before = new HashSet<>(prefs(c).getStringSet(KEY_APPROVED, new HashSet<>()));
        int removed = 0;
        for (String item : before) if (!item.equals(WORKER_PACKAGE + "|" + WORKER_SIGNER)) removed++;
        HashSet<String> keep = new HashSet<>();
        keep.add(WORKER_PACKAGE + "|" + WORKER_SIGNER);
        boolean committed = prefs(c).edit().putStringSet(KEY_APPROVED, keep).commit();
        if (!committed) { hardStopWithoutAudit(c); return -1; }
        Set<String> after = prefs(c).getStringSet(KEY_APPROVED, new HashSet<>());
        if (after.size() != 1 || !after.contains(WORKER_PACKAGE + "|" + WORKER_SIGNER)) { hardStopWithoutAudit(c); return -1; }
        if (!audit(c, "REVOKE_ALL_NON_DEFAULT", "TARGET_POSTCONDITION_CONFIRMED", "removed=" + removed, "")) return -1;
        return removed;
    }

    static String[] listApprovedPackages(Context c) {
        ArrayList<String> items = new ArrayList<>(prefs(c).getStringSet(KEY_APPROVED, new HashSet<>()));
        Collections.sort(items);
        return items.toArray(new String[0]);
    }

    static boolean validPackageName(String pkg) {
        if (pkg == null || pkg.length() < 3 || pkg.length() > 255) return false;
        return pkg.matches("[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z0-9_]+)+");
    }

    static String sha256String(String s) { return sha256Bytes((s == null ? "" : s).getBytes(StandardCharsets.UTF_8)); }

    static String sha256Bytes(byte[] data) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] out = md.digest(data);
            StringBuilder sb = new StringBuilder(out.length * 2);
            for (byte b : out) sb.append(String.format(Locale.ROOT, "%02x", b & 0xff));
            return sb.toString();
        } catch (Throwable t) { return "HASH_ERROR"; }
    }

    static void saveState(Context c, String action, String status, String resultDigest, String failure) {
        prefs(c).edit()
                .putString("last_action", safe(action))
                .putString("status", safe(status))
                .putString("result_digest", safe(resultDigest))
                .putString("failure", safe(failure))
                .commit();
        audit(c, action, status, resultDigest, failure);
    }

    static synchronized boolean preActionAudit(Context c, String action, String safeMetadata) {
        ensureDefaults(c);
        AuditChain.Verification before = verifyAuditIntegrity(c);
        if (!before.ok) {
            hardStopWithoutAudit(c);
            return false;
        }
        boolean ok = audit(c, action + "_PRE", "ACCEPTED", safeMetadata == null ? "" : safeMetadata, "");
        if (!ok) hardStopWithoutAudit(c);
        return ok;
    }

    static synchronized boolean audit(Context c, String action, String status, String result, String failure) {
        try {
            ensureDefaults(c);
            SharedPreferences p = prefs(c);
            long count = p.getLong(KEY_AUDIT_COUNT, 0L);
            if (count >= AUDIT_MAX_RECORDS_PER_SEGMENT && !rotate(c, p)) {
                hardStopWithoutAudit(c);
                return false;
            }
            p = prefs(c);
            long seq = p.getLong(KEY_AUDIT_SEQ, 0L) + 1L;
            long segment = p.getLong(KEY_AUDIT_SEGMENT, 0L);
            String prev = p.getString(KEY_AUDIT_HEAD, AuditChain.GENESIS);
            String resultHash = sha256String(result == null ? "" : result);
            String line = AuditChain.buildLine(seq, segment, PROCESS_SESSION_ID, Process.myPid(), bootCount(c),
                    SystemClock.elapsedRealtime(), System.currentTimeMillis(), action, status, resultHash, failure, prev);
            String entryHash = line.substring(line.lastIndexOf("|entry_hash=") + "|entry_hash=".length());
            try (FileOutputStream fos = c.openFileOutput(AUDIT_CURRENT, Context.MODE_APPEND)) {
                fos.write((line + "\n").getBytes(StandardCharsets.UTF_8));
                fos.getFD().sync();
            }
            boolean committed = p.edit().putLong(KEY_AUDIT_SEQ, seq).putString(KEY_AUDIT_HEAD, entryHash)
                    .putLong(KEY_AUDIT_COUNT, p.getLong(KEY_AUDIT_COUNT, 0L) + 1L)
                    .putString("last_audit", line).commit();
            if (!committed) { hardStopWithoutAudit(c); return false; }
            return true;
        } catch (Throwable ignored) { hardStopWithoutAudit(c); return false; }
    }

    private static void hardStopWithoutAudit(Context c) {
        armedUntilElapsed = 0L;
        armedPid = -1;
        armedBootCount = Integer.MIN_VALUE;
        armedSession = "";
        try { prefs(c).edit().putBoolean(KEY_EMERGENCY, true).commit(); } catch (Throwable ignored) {}
    }

    private static boolean rotate(Context c, SharedPreferences p) {
        File cur = new File(c.getFilesDir(), AUDIT_CURRENT);
        File prev = new File(c.getFilesDir(), AUDIT_PREVIOUS);
        if (!cur.exists()) return false;
        if (prev.exists() && !prev.delete()) return false;
        if (!cur.renameTo(prev)) return false;
        long curStartSeq = p.getLong(KEY_CUR_START_SEQ, 1L);
        String curStartPrev = p.getString(KEY_CUR_START_PREV, AuditChain.GENESIS);
        long nextSeq = p.getLong(KEY_AUDIT_SEQ, 0L) + 1L;
        String head = p.getString(KEY_AUDIT_HEAD, AuditChain.GENESIS);
        return p.edit()
                .putLong(KEY_PREV_START_SEQ, curStartSeq)
                .putString(KEY_PREV_START_PREV, curStartPrev)
                .putLong(KEY_CUR_START_SEQ, nextSeq)
                .putString(KEY_CUR_START_PREV, head)
                .putLong(KEY_AUDIT_SEGMENT, p.getLong(KEY_AUDIT_SEGMENT, 0L) + 1L)
                .putLong(KEY_AUDIT_COUNT, 0L)
                .commit();
    }

    static AuditChain.Verification verifyAuditIntegrity(Context c) {
        try {
            SharedPreferences p = prefs(c);
            File prev = new File(c.getFilesDir(), AUDIT_PREVIOUS);
            File cur = new File(c.getFilesDir(), AUDIT_CURRENT);
            List<String> lines = new ArrayList<>();
            long startSeq;
            String startPrev;
            if (prev.exists()) {
                lines.addAll(readLines(prev));
                startSeq = p.getLong(KEY_PREV_START_SEQ, 1L);
                startPrev = p.getString(KEY_PREV_START_PREV, AuditChain.GENESIS);
            } else {
                startSeq = p.getLong(KEY_CUR_START_SEQ, 1L);
                startPrev = p.getString(KEY_CUR_START_PREV, AuditChain.GENESIS);
            }
            if (cur.exists()) lines.addAll(readLines(cur));
            return AuditChain.verify(lines.toArray(new String[0]), startSeq, startPrev,
                    p.getLong(KEY_AUDIT_SEQ, 0L), p.getString(KEY_AUDIT_HEAD, AuditChain.GENESIS));
        } catch (Throwable t) { return new AuditChain.Verification(false, "VERIFY_EXCEPTION", 0); }
    }

    private static List<String> readLines(File f) throws Exception {
        ArrayList<String> out = new ArrayList<>();
        try (BufferedReader br = new BufferedReader(new InputStreamReader(new FileInputStream(f), StandardCharsets.UTF_8))) {
            String line; while ((line = br.readLine()) != null) out.add(line);
        }
        return out;
    }

    private static String safe(String s) {
        if (s == null) return "";
        return s.replace("\n", " ").replace("\r", " ").replace("\t", " ").replace("|", "/");
    }

    static final class PackageDescriptor {
        final String packageName, label, signer; final boolean launchable;
        PackageDescriptor(String packageName, String label, String signer, boolean launchable) {
            this.packageName = packageName; this.label = label; this.signer = signer; this.launchable = launchable;
        }
        String wire() { return safe(label) + "\t" + packageName + "\t" + signer + "\t" + launchable; }
    }
}
