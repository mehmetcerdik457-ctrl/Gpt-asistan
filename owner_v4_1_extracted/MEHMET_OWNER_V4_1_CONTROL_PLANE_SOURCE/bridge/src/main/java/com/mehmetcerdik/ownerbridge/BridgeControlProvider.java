package com.mehmetcerdik.ownerbridge;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.os.Binder;
import android.os.Bundle;

import java.util.ArrayList;

public final class BridgeControlProvider extends ContentProvider {
    @Override public boolean onCreate() {
        Context c = getContext();
        if (c != null) {
            BridgeSecurity.ensureDefaults(c);
            BridgeSecurity.forceFailClosed(c, "PROVIDER_PROCESS_CREATE");
        }
        return true;
    }

    @Override public String getType(Uri uri) { return null; }
    @Override public Cursor query(Uri uri, String[] projection, String selection, String[] selectionArgs, String sortOrder) { return null; }
    @Override public Uri insert(Uri uri, ContentValues values) { return null; }
    @Override public int delete(Uri uri, String selection, String[] selectionArgs) { return 0; }
    @Override public int update(Uri uri, ContentValues values, String selection, String[] selectionArgs) { return 0; }

    @Override public Bundle call(String method, String arg, Bundle extras) {
        Context c = getContext();
        if (c == null) return fail("NO_CONTEXT");
        if (!authCaller(c)) return fail("CALLER_UID_PACKAGE_SIGNER_AUTH_FAILED");
        if (method == null) return fail("NULL_METHOD");
        BridgeAccessibilityService svc = BridgeAccessibilityService.instance();

        switch (method) {
            case "status": return statusBundle(c, svc);
            case "arm": {
                long ttl = extras == null ? BridgeSecurity.DEFAULT_ARM_MS : extras.getLong("ttl_ms", BridgeSecurity.DEFAULT_ARM_MS);
                if(!BridgeSecurity.preActionAudit(c,"ARM","requested_ttl_ms="+ttl)) return fail("AUDIT_PRECOMMIT_FAILED");
                long granted = BridgeSecurity.arm(c, ttl);
                Bundle b = statusBundle(c, svc);
                b.putLong("granted_ttl_ms", BridgeSecurity.isArmed(c) ? granted : 0L);
                b.putString("session_class", BridgeSecurity.SESSION_CLASS);
                return b;
            }
            case "stop": BridgeSecurity.stop(c); return statusBundle(c, svc);
            case "listPackages": {
                if (!BridgeSecurity.isArmed(c)) return fail("NOT_ARMED_OR_EMERGENCY_STOP");
                if(!BridgeSecurity.preActionAudit(c,"LIST_PACKAGES","")) return fail("AUDIT_PRECOMMIT_FAILED");
                ArrayList<String> out = new ArrayList<>();
                for (BridgeSecurity.PackageDescriptor d : BridgeSecurity.listLaunchablePackages(c)) out.add(d.wire());
                Bundle b = ok(); b.putString("status", "OBSERVED"); b.putStringArrayList("packages", out); return b;
            }
            case "inspectPackage": {
                if (!BridgeSecurity.isArmed(c)) return fail("NOT_ARMED_OR_EMERGENCY_STOP");
                String pkg = extras == null ? null : extras.getString("package");
                if(!BridgeSecurity.preActionAudit(c,"INSPECT_PACKAGE","package="+pkg)) return fail("AUDIT_PRECOMMIT_FAILED");
                BridgeSecurity.PackageDescriptor d = BridgeSecurity.inspectInstalledPackage(c, pkg);
                if (d == null) return fail("PACKAGE_INSPECTION_FAILED");
                Bundle b=ok(); b.putString("status","OBSERVED"); b.putString("package",d.packageName); b.putString("label",d.label); b.putString("signer",d.signer); b.putBoolean("launchable",d.launchable); return b;
            }
            case "approvePackage": {
                if (!BridgeSecurity.isArmed(c)) return fail("NOT_ARMED_OR_EMERGENCY_STOP");
                String pkg = extras == null ? null : extras.getString("package");
                if(!BridgeSecurity.preActionAudit(c,"APPROVE_PACKAGE","package="+pkg)) return fail("AUDIT_PRECOMMIT_FAILED");
                String signer = BridgeSecurity.approveInstalledPackage(c, pkg);
                if (signer == null) return fail("PACKAGE_APPROVAL_FAILED");
                Bundle b = ok(); b.putString("status", "TARGET_POSTCONDITION_CONFIRMED"); b.putString("package", pkg); b.putString("signer", signer); return b;
            }
            case "listApprovedPackages": {
                if(!BridgeSecurity.preActionAudit(c,"LIST_APPROVED_PACKAGES","")) return fail("AUDIT_PRECOMMIT_FAILED");
                Bundle b=ok(); b.putString("status","OBSERVED"); b.putStringArray("approved",BridgeSecurity.listApprovedPackages(c)); return b;
            }
            case "revokePackage": {
                String pkg = extras == null ? null : extras.getString("package");
                if (BridgeSecurity.WORKER_PACKAGE.equals(pkg)) return fail("DEFAULT_WORKER_REVOCATION_FORBIDDEN");
                if(!BridgeSecurity.preActionAudit(c,"REVOKE_PACKAGE","package="+pkg)) return fail("AUDIT_PRECOMMIT_FAILED");
                boolean changed=BridgeSecurity.revokePackage(c,pkg);
                Bundle b=ok(); b.putString("status",changed?"TARGET_POSTCONDITION_CONFIRMED":"OBSERVED"); b.putBoolean("revoked",changed); return b;
            }
            case "revokeAllNonDefaultPackages": {
                if(!BridgeSecurity.preActionAudit(c,"REVOKE_ALL_NON_DEFAULT","")) return fail("AUDIT_PRECOMMIT_FAILED");
                int removed=BridgeSecurity.revokeAllNonDefaultPackages(c);
                if (removed < 0) return fail("REVOCATION_PERSIST_OR_AUDIT_FAILED");
                Bundle b=ok(); b.putString("status","TARGET_POSTCONDITION_CONFIRMED"); b.putInt("removed",removed); return b;
            }
            case "verifyAudit": {
                AuditChain.Verification v=BridgeSecurity.verifyAuditIntegrity(c);
                Bundle b=v.ok?ok():fail(v.reason); b.putString("status",v.ok?"TARGET_POSTCONDITION_CONFIRMED":"FAILED"); b.putBoolean("audit_integrity",v.ok); b.putInt("records",v.records); return b;
            }
            case "screenRead": if (!ready(c, svc)) return fail("BRIDGE_NOT_READY"); if(!BridgeSecurity.preActionAudit(c,"SCREEN_READ","")) return fail("AUDIT_PRECOMMIT_FAILED"); return record(c, "SCREEN_READ", svc.screenRead(), "");
            case "clickText": {
                if (!ready(c, svc)) return fail("BRIDGE_NOT_READY");
                String text = extras == null ? null : extras.getString("text");
                String meta="selector_hash=" + BridgeSecurity.sha256String(text); if(!BridgeSecurity.preActionAudit(c,"CLICK_TEXT",meta)) return fail("AUDIT_PRECOMMIT_FAILED");
                return record(c, "CLICK_TEXT", svc.clickTextExact(text), meta);
            }
            case "typeText": {
                if (!ready(c, svc)) return fail("BRIDGE_NOT_READY");
                String selector = extras == null ? null : extras.getString("selector");
                String text = extras == null ? null : extras.getString("text");
                boolean secret = extras != null && extras.getBoolean("secret", false);
                String safeMeta = "selector_hash=" + BridgeSecurity.sha256String(selector) + "|text_len=" + (text == null ? -1 : text.length()) + "|secret=" + secret;
                if(!BridgeSecurity.preActionAudit(c,"TYPE_TEXT",safeMeta)) return fail("AUDIT_PRECOMMIT_FAILED");
                return record(c, "TYPE_TEXT", svc.typeText(selector, text, secret), safeMeta);
            }
            case "scroll": {
                if (!ready(c, svc)) return fail("BRIDGE_NOT_READY");
                boolean forward = extras == null || extras.getBoolean("forward", true); String meta="forward="+forward;
                if(!BridgeSecurity.preActionAudit(c,"SCROLL",meta)) return fail("AUDIT_PRECOMMIT_FAILED");
                return record(c, "SCROLL", svc.scroll(forward), meta);
            }
            case "swipe": {
                if (!ready(c, svc)) return fail("BRIDGE_NOT_READY"); if (extras == null) return fail("MISSING_EXTRAS");
                float sx=extras.getFloat("sx",-1f), sy=extras.getFloat("sy",-1f), ex=extras.getFloat("ex",-1f), ey=extras.getFloat("ey",-1f); long duration=extras.getLong("duration_ms",350L);
                String meta="coords="+sx+","+sy+","+ex+","+ey+"|duration="+duration; if(!BridgeSecurity.preActionAudit(c,"SWIPE",meta)) return fail("AUDIT_PRECOMMIT_FAILED");
                return record(c,"SWIPE",svc.swipe(sx,sy,ex,ey,duration),meta);
            }
            case "globalAction": {
                if (!ready(c, svc)) return fail("BRIDGE_NOT_READY"); String action=extras==null?null:extras.getString("action"); String meta="action="+action;
                if(!BridgeSecurity.preActionAudit(c,"GLOBAL_ACTION",meta)) return fail("AUDIT_PRECOMMIT_FAILED"); return record(c,"GLOBAL_ACTION",svc.globalAction(action),meta);
            }
            case "launchApp": {
                if (!ready(c, svc)) return fail("BRIDGE_NOT_READY"); String pkg=extras==null?null:extras.getString("package"); String meta="package="+pkg;
                if(!BridgeSecurity.preActionAudit(c,"LAUNCH_APP",meta)) return fail("AUDIT_PRECOMMIT_FAILED"); return record(c,"LAUNCH_APP",svc.launchApp(pkg),meta);
            }
            case "verifyPostcondition": {
                if (!ready(c, svc)) return fail("BRIDGE_NOT_READY");
                String kind=extras==null?null:extras.getString("kind"); String expected=extras==null?null:extras.getString("expected"); String meta="kind="+kind+"|expected_hash="+BridgeSecurity.sha256String(expected);
                if(!BridgeSecurity.preActionAudit(c,"VERIFY_POSTCONDITION",meta)) return fail("AUDIT_PRECOMMIT_FAILED"); return record(c,"VERIFY_POSTCONDITION",svc.verifyPostcondition(kind,expected),meta);
            }
            default: return fail("UNKNOWN_OR_INVALID_METHOD");
        }
    }

    private boolean ready(Context c, BridgeAccessibilityService svc) { return svc != null && BridgeSecurity.isArmed(c) && !BridgeSecurity.isEmergencyStopped(c); }

    private Bundle record(Context c, String action, Bundle result, String safeMetadata) {
        if (result == null) result = fail("NULL_RESULT");
        String status=result.getString("status",result.getBoolean("ok",false)?"OBSERVED":"FAILED");
        String failure=result.getString("failure","");
        String digestInput=(safeMetadata==null?"":safeMetadata)+"|snapshot_hash="+result.getString("snapshot_hash","")+"|package="+result.getString("package","");
        BridgeSecurity.saveState(c,action,status,BridgeSecurity.sha256String(digestInput),failure);
        if(BridgeSecurity.isEmergencyStopped(c) && !"FAILED".equals(status)){ Bundle b=fail("AUDIT_POSTCOMMIT_FAILED_FAIL_CLOSED"); b.putString("original_status",status); return b; }
        return result;
    }

    private boolean authCaller(Context c) {
        int uid=Binder.getCallingUid(); PackageManager pm=c.getPackageManager(); String[] pkgs=pm.getPackagesForUid(uid);
        if (pkgs==null || pkgs.length!=1) return false;
        if (!BridgeSecurity.CORE_PACKAGE.equals(pkgs[0])) return false;
        return BridgeSecurity.verifyCore(c);
    }

    private Bundle statusBundle(Context c, BridgeAccessibilityService svc) {
        Bundle b=ok(); b.putBoolean("core_ok",BridgeSecurity.verifyCore(c)); b.putBoolean("service_connected",svc!=null);
        b.putBoolean("armed",BridgeSecurity.isArmed(c)); b.putBoolean("emergency_stop",BridgeSecurity.isEmergencyStopped(c));
        b.putLong("armed_remaining_ms",BridgeSecurity.armedRemainingMs(c)); b.putString("session_class",BridgeSecurity.SESSION_CLASS);
        b.putString("status",BridgeSecurity.prefs(c).getString("status","OBSERVED")); b.putString("failure",BridgeSecurity.prefs(c).getString("failure",""));
        b.putString("last_action",BridgeSecurity.prefs(c).getString("last_action","")); b.putString("last_audit",BridgeSecurity.prefs(c).getString("last_audit",""));
        AuditChain.Verification av=BridgeSecurity.verifyAuditIntegrity(c); b.putBoolean("audit_integrity",av.ok); b.putString("audit_integrity_reason",av.reason);
        if (svc!=null) b.putAll(svc.status()); return b;
    }

    private Bundle ok(){ Bundle b=new Bundle(); b.putBoolean("ok",true); return b; }
    private Bundle fail(String reason){ Bundle b=new Bundle(); b.putBoolean("ok",false); b.putString("status","FAILED"); b.putString("failure",reason); return b; }
}
