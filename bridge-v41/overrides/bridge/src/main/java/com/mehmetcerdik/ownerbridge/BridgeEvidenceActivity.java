package com.mehmetcerdik.ownerbridge;

import android.accessibilityservice.AccessibilityService;
import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.content.pm.SigningInfo;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileReader;
import java.security.MessageDigest;
import java.util.Locale;

public final class BridgeEvidenceActivity extends Activity {
    private static final String SOURCE_ZIP_SHA256 = "7df6d150b9159affe69e529fdf1ada3ce8f957ffb1c99ba7c55f8fe3eefd7628";
    private static final String EXPECTED_PACKAGE = "com.mehmetcerdik.ownerbridge";
    private static final String EXPECTED_VERSION_NAME = "1.1.0";
    private static final long EXPECTED_VERSION_CODE = 2L;

    private TextView output;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int p=(int)(16*getResources().getDisplayMetrics().density);
        root.setPadding(p,p,p,p);

        TextView title = new TextView(this);
        title.setText("MEHMET PRIVILEGED BRIDGE — FINAL EVIDENCE");
        title.setTextSize(20f);
        root.addView(title);

        Button refresh = new Button(this);
        refresh.setText("Kanıtı Yenile");
        refresh.setOnClickListener(v -> refresh());
        root.addView(refresh);

        Button copy = new Button(this);
        copy.setText("Final Bridge Kanıtını Kopyala");
        copy.setOnClickListener(v -> {
            String evidence = buildEvidence().toString();
            ClipboardManager cm=(ClipboardManager)getSystemService(CLIPBOARD_SERVICE);
            cm.setPrimaryClip(ClipData.newPlainText("MEHMET Bridge final evidence", evidence));
            output.setText(evidence);
        });
        root.addView(copy);

        output = new TextView(this);
        output.setTextSize(11f);
        output.setTextIsSelectable(true);
        root.addView(output);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(root);
        setContentView(scroll);
        refresh();
    }

    @Override protected void onResume() {
        super.onResume();
        if (output != null) refresh();
    }

    private void refresh() {
        output.setText(buildEvidence().toString());
    }

    private JSONObject buildEvidence() {
        JSONObject out = new JSONObject();
        try {
            PackageInfo self = packageInfo(getPackageName());
            String selfHash = sha256(new File(getApplicationInfo().sourceDir));
            String selfSigner = signerSha256(self);
            boolean packageMatch = EXPECTED_PACKAGE.equals(getPackageName());
            boolean versionMatch = EXPECTED_VERSION_NAME.equals(self.versionName) && versionCode(self) == EXPECTED_VERSION_CODE;
            boolean signerMatch = BridgeSecurity.CORE_SIGNER.equalsIgnoreCase(selfSigner);
            boolean noInternet = getPackageManager().checkPermission("android.permission.INTERNET", getPackageName())
                    != PackageManager.PERMISSION_GRANTED;

            JSONObject owner = installedIdentity(BridgeSecurity.CORE_PACKAGE);
            boolean ownerMatch = owner.optBoolean("installed", false)
                    && "1.2.0".equals(owner.optString("version_name"))
                    && owner.optLong("version_code", -1) == 4L
                    && BridgeSecurity.CORE_SIGNER.equalsIgnoreCase(owner.optString("signer_cert_sha256"));

            boolean accessibilityEnabled = accessibilityEnabled();
            boolean serviceConnected = BridgeAccessibilityService.instance() != null;
            AuditChain.Verification audit = BridgeSecurity.verifyAuditIntegrity(this);
            JSONArray events = retainedAuditEvents();

            boolean launchPass = has(events, "LAUNCH_APP", "TARGET_POSTCONDITION_CONFIRMED");
            boolean swipePass = hasAny(events, "SWIPE", new String[]{"GESTURE_COMPLETED","UI_CHANGED","TARGET_POSTCONDITION_CONFIRMED"});
            boolean typePass = has(events, "TYPE_TEXT", "TARGET_POSTCONDITION_CONFIRMED");
            boolean postconditionPass = launchPass && typePass;
            boolean recordPass = audit.ok && audit.records > 0 && events.length() > 0;

            out.put("version", 1);
            out.put("status", packageMatch && versionMatch && signerMatch && noInternet && ownerMatch
                    && accessibilityEnabled && serviceConnected && audit.ok
                    && launchPass && swipePass && typePass && postconditionPass && recordPass
                    ? "FULL_BRIDGE_EVIDENCE_CAPTURED" : "FULL_BRIDGE_EVIDENCE_PENDING");
            out.put("source_zip_sha256", SOURCE_ZIP_SHA256);
            out.put("bridge", new JSONObject()
                    .put("package_name", getPackageName())
                    .put("version_name", self.versionName == null ? "" : self.versionName)
                    .put("version_code", Long.toString(versionCode(self)))
                    .put("artifact_sha256", selfHash)
                    .put("signer_cert_sha256", selfSigner)
                    .put("package_match", packageMatch)
                    .put("version_match", versionMatch)
                    .put("signer_match", signerMatch)
                    .put("network_permission", noInternet ? "NONE" : "PRESENT")
                    .put("accessibility_enabled", accessibilityEnabled)
                    .put("service_connected", serviceConnected)
                    .put("armed", BridgeSecurity.isArmed(this))
                    .put("emergency_stop", BridgeSecurity.isEmergencyStopped(this)));
            out.put("owner", owner);
            out.put("runtime", new JSONObject()
                    .put("launch_pass", launchPass)
                    .put("swipe_pass", swipePass)
                    .put("type_pass", typePass)
                    .put("postcondition_pass", postconditionPass)
                    .put("record_pass", recordPass)
                    .put("audit_integrity", audit.ok)
                    .put("audit_integrity_reason", audit.reason)
                    .put("audit_records", audit.records)
                    .put("events", events));
            out.put("captured_at_epoch_ms", System.currentTimeMillis());
        } catch (Throwable t) {
            try {
                out.put("version",1);
                out.put("status","FULL_BRIDGE_EVIDENCE_ERROR");
                out.put("failure",t.getClass().getSimpleName());
            } catch (Throwable ignored) {}
        }
        return out;
    }

    private JSONObject installedIdentity(String pkg) {
        JSONObject o=new JSONObject();
        try {
            PackageInfo pi=packageInfo(pkg);
            o.put("installed",true);
            o.put("package_name",pkg);
            o.put("version_name",pi.versionName==null?"":pi.versionName);
            o.put("version_code",versionCode(pi));
            o.put("signer_cert_sha256",signerSha256(pi));
            o.put("artifact_sha256",sha256(new File(pi.applicationInfo.sourceDir)));
        } catch (Throwable t) {
            try { o.put("installed",false); o.put("package_name",pkg); } catch (Throwable ignored) {}
        }
        return o;
    }

    private PackageInfo packageInfo(String pkg) throws Exception {
        if (Build.VERSION.SDK_INT >= 28) return getPackageManager().getPackageInfo(pkg, PackageManager.GET_SIGNING_CERTIFICATES);
        @SuppressWarnings("deprecation")
        PackageInfo pi=getPackageManager().getPackageInfo(pkg, PackageManager.GET_SIGNATURES);
        return pi;
    }

    private long versionCode(PackageInfo pi) {
        if (Build.VERSION.SDK_INT >= 28) return pi.getLongVersionCode();
        @SuppressWarnings("deprecation") long v=pi.versionCode;
        return v;
    }

    private String signerSha256(PackageInfo pi) throws Exception {
        Signature[] sigs;
        if (Build.VERSION.SDK_INT >= 28) {
            SigningInfo si=pi.signingInfo;
            sigs=si==null?null:si.getApkContentsSigners();
        } else {
            @SuppressWarnings("deprecation") Signature[] legacy=pi.signatures;
            sigs=legacy;
        }
        if (sigs==null || sigs.length!=1) return "";
        return sha256Bytes(sigs[0].toByteArray());
    }

    private boolean accessibilityEnabled() {
        String enabled=Settings.Secure.getString(getContentResolver(), Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
        if (enabled==null) return false;
        String expected=BridgeAccessibilityService.class.getName();
        for (String flat: enabled.split(":")) {
            ComponentName c=ComponentName.unflattenFromString(flat);
            if (c!=null && getPackageName().equals(c.getPackageName()) && expected.equals(c.getClassName())) return true;
        }
        return false;
    }

    private JSONArray retainedAuditEvents() {
        JSONArray out=new JSONArray();
        appendAudit(out,new File(getFilesDir(),"owner_audit_previous.log"));
        appendAudit(out,new File(getFilesDir(),"owner_audit_current.log"));
        return out;
    }

    private void appendAudit(JSONArray out, File file) {
        if (!file.exists()) return;
        try (BufferedReader br=new BufferedReader(new FileReader(file))) {
            String line;
            while ((line=br.readLine())!=null) {
                if (line.trim().isEmpty()) continue;
                JSONObject e=new JSONObject();
                e.put("seq",parse(line,"seq"));
                e.put("action",parse(line,"action"));
                e.put("status",parse(line,"status"));
                e.put("failure",parse(line,"failure"));
                e.put("entry_hash",parse(line,"entry_hash"));
                out.put(e);
            }
        } catch (Throwable ignored) {}
    }

    private String parse(String line,String key) {
        String prefix=key+"=";
        for (String part: line.split("\\|",-1)) if (part.startsWith(prefix)) return part.substring(prefix.length());
        return "";
    }

    private boolean has(JSONArray events,String action,String status) {
        for (int i=0;i<events.length();i++) {
            JSONObject e=events.optJSONObject(i);
            if (e!=null && action.equals(e.optString("action")) && status.equals(e.optString("status"))) return true;
        }
        return false;
    }

    private boolean hasAny(JSONArray events,String action,String[] statuses) {
        for (String status:statuses) if (has(events,action,status)) return true;
        return false;
    }

    private String sha256(File f) throws Exception {
        MessageDigest md=MessageDigest.getInstance("SHA-256");
        byte[] buf=new byte[65536];
        try(FileInputStream in=new FileInputStream(f)) {
            int n; while((n=in.read(buf))>0) md.update(buf,0,n);
        }
        return hex(md.digest());
    }

    private String sha256Bytes(byte[] bytes) throws Exception {
        return hex(MessageDigest.getInstance("SHA-256").digest(bytes));
    }

    private String hex(byte[] data) {
        StringBuilder sb=new StringBuilder(data.length*2);
        for(byte b:data) sb.append(String.format(Locale.ROOT,"%02x",b & 0xff));
        return sb.toString();
    }
}
