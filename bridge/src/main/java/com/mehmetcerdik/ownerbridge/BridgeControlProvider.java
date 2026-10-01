package com.mehmetcerdik.ownerbridge;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.os.Binder;
import android.os.Bundle;

public final class BridgeControlProvider extends ContentProvider {
    @Override public boolean onCreate() {
        Context c = getContext();
        if (c != null) BridgeSecurity.ensureDefaults(c);
        return true;
    }

    @Override public String getType(Uri u) { return null; }
    @Override public Cursor query(Uri u, String[] p, String s, String[] a, String o) { return null; }
    @Override public Uri insert(Uri u, ContentValues v) { return null; }
    @Override public int delete(Uri u, String s, String[] a) { return 0; }
    @Override public int update(Uri u, ContentValues v, String s, String[] a) { return 0; }

    @Override public Bundle call(String method, String arg, Bundle extras) {
        Context c = getContext();
        if (c == null) return fail("NO_CONTEXT");
        if (!auth(c)) return fail("CALLER_UID_PACKAGE_SIGNER_AUTH_FAILED");
        if (method == null) return fail("NULL_METHOD");
        BridgeAccessibilityService service = BridgeAccessibilityService.instance();

        switch (method) {
            case "status":
                return status(c, service);
            case "arm": {
                long ttl = extras == null ? BridgeSecurity.DEFAULT_ARM_MS
                        : extras.getLong("ttl_ms", BridgeSecurity.DEFAULT_ARM_MS);
                long until = BridgeSecurity.arm(c, ttl);
                Bundle b = status(c, service);
                b.putLong("armed_until_elapsed", until);
                return b;
            }
            case "stop":
                BridgeSecurity.stop(c);
                return status(c, service);
            case "approvePackage": {
                if (!BridgeSecurity.isArmed(c)) return fail("NOT_ARMED_OR_EMERGENCY_STOP");
                String pkg = extras == null ? null : extras.getString("package");
                String signer = BridgeSecurity.approveInstalledPackage(c, pkg);
                if (signer == null) return fail("FIXED_PACKAGE_VERIFICATION_FAILED");
                Bundle b = ok();
                b.putString("status", "CONFIRMED");
                b.putString("package", pkg);
                b.putString("signer", signer);
                return b;
            }
            case "revokePackage":
                return fail("DYNAMIC_PACKAGE_REVOCATION_DISABLED_FIXED_ALLOWLIST");
            case "screenRead":
                if (!ready(c, service)) return fail("BRIDGE_NOT_READY");
                return service.screenRead();
            case "findElement":
                if (!ready(c, service)) return fail("BRIDGE_NOT_READY");
                return service.findElement(
                        extras == null ? null : extras.getString("text"),
                        extras == null ? null : extras.getString("role"));
            case "clickText":
                if (!ready(c, service)) return fail("BRIDGE_NOT_READY");
                return service.clickTextExact(extras == null ? null : extras.getString("text"));
            case "typeText":
                if (!ready(c, service)) return fail("BRIDGE_NOT_READY");
                return service.typeText(
                        extras == null ? null : extras.getString("selector"),
                        extras == null ? null : extras.getString("text"));
            case "scroll":
                if (!ready(c, service)) return fail("BRIDGE_NOT_READY");
                return service.scroll(extras == null || extras.getBoolean("forward", true));
            case "swipe":
                if (!ready(c, service)) return fail("BRIDGE_NOT_READY");
                if (extras == null) return fail("MISSING_EXTRAS");
                return service.swipe(
                        extras.getFloat("sx", -1),
                        extras.getFloat("sy", -1),
                        extras.getFloat("ex", -1),
                        extras.getFloat("ey", -1),
                        extras.getLong("duration_ms", 350));
            case "globalAction":
                if (!ready(c, service)) return fail("BRIDGE_NOT_READY");
                return service.globalAction(extras == null ? null : extras.getString("action"));
            case "launchApp":
                if (!ready(c, service)) return fail("BRIDGE_NOT_READY");
                return service.launchApp(extras == null ? null : extras.getString("package"));
            case "clearEvidence":
                if (!BridgeSecurity.isArmed(c)) return fail("NOT_ARMED_OR_EMERGENCY_STOP");
                BridgeEvidenceStore.clear(c);
                return ok();
            default:
                return fail("UNKNOWN_OR_INVALID_METHOD");
        }
    }

    private boolean ready(Context c, BridgeAccessibilityService s) {
        return s != null && BridgeSecurity.isArmed(c) && !BridgeSecurity.isEmergencyStopped(c);
    }

    private boolean auth(Context c) {
        String[] packages = c.getPackageManager().getPackagesForUid(Binder.getCallingUid());
        return packages != null && packages.length == 1
                && BridgeSecurity.CORE_PACKAGE.equals(packages[0])
                && BridgeSecurity.verifyCore(c);
    }

    private Bundle status(Context c, BridgeAccessibilityService s) {
        Bundle b = ok();
        b.putBoolean("core_ok", BridgeSecurity.verifyCore(c));
        b.putBoolean("service_connected", s != null);
        b.putBoolean("armed", BridgeSecurity.isArmed(c));
        b.putBoolean("emergency_stop", BridgeSecurity.isEmergencyStopped(c));
        b.putString("status", s == null ? "SERVICE_NOT_CONNECTED" : "READY");
        if (s != null) b.putAll(s.status());
        return b;
    }

    private Bundle ok() {
        Bundle b = new Bundle();
        b.putBoolean("ok", true);
        return b;
    }

    private Bundle fail(String reason) {
        Bundle b = new Bundle();
        b.putBoolean("ok", false);
        b.putString("status", "FAILED");
        b.putString("failure", reason);
        return b;
    }
}
