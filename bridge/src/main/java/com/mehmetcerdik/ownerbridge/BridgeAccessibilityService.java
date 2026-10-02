package com.mehmetcerdik.ownerbridge;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.content.Intent;
import android.graphics.Path;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class BridgeAccessibilityService extends AccessibilityService {
    private static volatile BridgeAccessibilityService INSTANCE;
    static BridgeAccessibilityService instance() { return INSTANCE; }

    @Override protected void onServiceConnected() {
        super.onServiceConnected();
        INSTANCE = this;
        BridgeSecurity.ensureDefaults(this);
        BridgeEvidenceStore.record(this, "SERVICE", "READY", "connected");
    }

    @Override public void onDestroy() {
        if (INSTANCE == this) INSTANCE = null;
        BridgeEvidenceStore.record(this, "SERVICE", "STOPPED", "");
        super.onDestroy();
    }

    @Override public void onInterrupt() {
        BridgeEvidenceStore.record(this, "SERVICE", "INTERRUPTED", "");
    }

    @Override public void onAccessibilityEvent(AccessibilityEvent e) {
        if (e != null && e.getPackageName() != null) {
            String pkg = e.getPackageName().toString();
            if (BridgeSecurity.isFixedApprovedPackage(pkg)) {
                BridgeEvidenceStore.record(this, "WINDOW", "OBSERVED", pkg);
            }
        }
    }

    Bundle status() {
        Bundle b = ok();
        b.putString("active_package", activePackage());
        b.putBoolean("service_connected", true);
        return b;
    }

    Bundle screenRead() {
        AccessibilityNodeInfo root = freshApprovedRoot();
        if (root == null) return fail("NO_APPROVED_ACTIVE_ROOT");
        String snapshot = snapshot(root);
        BridgeEvidenceStore.record(this, "SCREEN_READ", "PASS", BridgeSecurity.sha256String(snapshot));
        Bundle b = ok();
        b.putString("status", "OBSERVED");
        b.putString("active_package", pkg(root));
        b.putString("snapshot", snapshot);
        b.putString("snapshot_hash", BridgeSecurity.sha256String(snapshot));
        b.putBoolean("sensitive_surface", sensitiveSurface(root));
        b.putBoolean("confirmed", true);
        return b;
    }

    Bundle findElement(String text, String role) {
        AccessibilityNodeInfo root = freshApprovedRoot();
        if (root == null) return fail("NO_APPROVED_ACTIVE_ROOT");
        List<AccessibilityNodeInfo> found = new ArrayList<>();
        String r = role == null ? "" : role.trim().toLowerCase(Locale.ROOT);
        String q = text == null ? "" : text.trim();
        if ("editable".equals(r)) {
            collectEditable(root, found);
        } else if (!q.isEmpty()) {
            collectLabel(root, q, found);
        } else {
            return fail("FIND_ELEMENT_CRITERIA_REQUIRED");
        }
        Bundle b = ok();
        b.putString("active_package", pkg(root));
        b.putInt("match_count", found.size());
        b.putBoolean("exists", found.size() == 1);
        b.putBoolean("confirmed", found.size() == 1);
        if (found.size() == 1) {
            AccessibilityNodeInfo node = found.get(0);
            b.putString("class_name", String.valueOf(node.getClassName()));
            b.putString("view_id", node.getViewIdResourceName() == null ? "" : node.getViewIdResourceName());
            b.putString("label_hash", BridgeSecurity.sha256String(label(node)));
        }
        if (found.size() != 1) {
            b.putBoolean("ok", false);
            b.putString("failure", found.isEmpty() ? "ELEMENT_NOT_FOUND" : "ELEMENT_AMBIGUOUS");
        }
        return b;
    }

    Bundle clickTextExact(String wanted) {
        if (wanted == null || wanted.trim().isEmpty()) return fail("EMPTY_SELECTOR");
        AccessibilityNodeInfo root = freshApprovedRoot();
        if (root == null) return fail("NO_APPROVED_ACTIVE_ROOT");
        if (sensitiveSurface(root)) return fail("SENSITIVE_SURFACE_FAIL_CLOSED");
        String packageName = pkg(root);
        List<AccessibilityNodeInfo> matches = new ArrayList<>();
        collectLabel(root, wanted.trim(), matches);
        if (matches.size() != 1) return fail(matches.isEmpty() ? "CLICK_TARGET_NOT_FOUND" : "CLICK_TARGET_AMBIGUOUS");
        AccessibilityNodeInfo target = clickable(matches.get(0));
        if (target == null) return fail("CLICK_TARGET_NOT_CLICKABLE");
        if (!BridgeSecurity.isPackageApproved(this, packageName) || !packageName.equals(activePackage())) {
            return fail("TOCTOU_PACKAGE_CHANGED");
        }
        boolean dispatched = target.performAction(AccessibilityNodeInfo.ACTION_CLICK);
        SystemClock.sleep(180L);
        AccessibilityNodeInfo after = freshApprovedRoot();
        boolean confirmed = dispatched && after != null && packageName.equals(pkg(after));
        BridgeEvidenceStore.record(this, "CLICK_TEXT", confirmed ? "PASS" : "FAIL",
                BridgeSecurity.sha256String(wanted));
        Bundle b = confirmed ? ok() : fail("CLICK_POSTCONDITION_FAILED");
        if (confirmed) {
            b.putString("status", "TARGET_POSTCONDITION_CONFIRMED");
            b.putBoolean("confirmed", true);
            b.putString("active_package", packageName);
        }
        return b;
    }

    Bundle typeText(String selector, String value) {
        if (value == null || value.length() > 4000) return fail(value == null ? "NULL_TEXT" : "TEXT_TOO_LONG");
        AccessibilityNodeInfo root = freshApprovedRoot();
        if (root == null) return fail("NO_APPROVED_ACTIVE_ROOT");
        if (sensitiveSurface(root)) return fail("SENSITIVE_SURFACE_FAIL_CLOSED");
        String packageName = pkg(root);
        List<AccessibilityNodeInfo> editables = new ArrayList<>();
        collectEditable(root, editables);
        AccessibilityNodeInfo target;
        if (selector == null || selector.trim().isEmpty()) {
            if (editables.size() != 1) return fail(editables.isEmpty() ? "EDITABLE_NOT_FOUND" : "EDITABLE_AMBIGUOUS");
            target = editables.get(0);
        } else {
            List<AccessibilityNodeInfo> filtered = new ArrayList<>();
            for (AccessibilityNodeInfo n : editables) {
                if (label(n).equalsIgnoreCase(selector.trim())) filtered.add(n);
            }
            if (filtered.size() != 1) return fail(filtered.isEmpty() ? "EDITABLE_SELECTOR_NOT_FOUND" : "EDITABLE_SELECTOR_AMBIGUOUS");
            target = filtered.get(0);
        }
        if (target.isPassword()) return fail("PASSWORD_FIELD_REFUSED");
        if (!BridgeSecurity.isPackageApproved(this, packageName) || !packageName.equals(activePackage())) {
            return fail("TOCTOU_PACKAGE_CHANGED");
        }
        Bundle args = new Bundle();
        args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, value);
        if (!target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) return fail("SET_TEXT_DISPATCH_FAILED");
        SystemClock.sleep(150L);
        AccessibilityNodeInfo after = freshApprovedRoot();
        boolean confirmed = after != null && packageName.equals(pkg(after)) && findText(after, value);
        BridgeEvidenceStore.record(this, "TYPE_TEXT", confirmed ? "PASS" : "FAIL",
                "len=" + value.length());
        Bundle b = confirmed ? ok() : fail("TYPE_TEXT_POSTCONDITION_FAILED");
        if (confirmed) {
            b.putString("status", "TARGET_POSTCONDITION_CONFIRMED");
            b.putBoolean("confirmed", true);
            b.putString("active_package", packageName);
        }
        return b;
    }

    Bundle scroll(boolean forward) {
        AccessibilityNodeInfo root = freshApprovedRoot();
        if (root == null) return fail("NO_APPROVED_ACTIVE_ROOT");
        if (sensitiveSurface(root)) return fail("SENSITIVE_SURFACE_FAIL_CLOSED");
        String packageName = pkg(root);
        AccessibilityNodeInfo target = scrollable(root);
        if (target == null) return fail("SCROLLABLE_NOT_FOUND");
        boolean dispatched = target.performAction(
                forward ? AccessibilityNodeInfo.ACTION_SCROLL_FORWARD : AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD);
        SystemClock.sleep(150L);
        AccessibilityNodeInfo after = freshApprovedRoot();
        boolean confirmed = dispatched && after != null && packageName.equals(pkg(after));
        BridgeEvidenceStore.record(this, forward ? "SCROLL_FORWARD" : "SCROLL_BACKWARD", confirmed ? "PASS" : "FAIL", "");
        Bundle b = confirmed ? ok() : fail("SCROLL_POSTCONDITION_FAILED");
        if (confirmed) b.putBoolean("confirmed", true);
        return b;
    }

    Bundle swipe(float sx, float sy, float ex, float ey, long duration) {
        AccessibilityNodeInfo root = freshApprovedRoot();
        if (root == null) return fail("NO_APPROVED_ACTIVE_ROOT");
        if (sensitiveSurface(root)) return fail("SENSITIVE_SURFACE_FAIL_CLOSED");
        String packageName = pkg(root);
        if (!norm(sx) || !norm(sy) || !norm(ex) || !norm(ey)) return fail("SWIPE_COORDINATE_OUT_OF_RANGE");
        long d = Math.max(100, Math.min(duration <= 0 ? 350 : duration, 2000));
        android.util.DisplayMetrics dm = getResources().getDisplayMetrics();
        Path path = new Path();
        path.moveTo(sx * dm.widthPixels, sy * dm.heightPixels);
        path.lineTo(ex * dm.widthPixels, ey * dm.heightPixels);
        GestureDescription g = new GestureDescription.Builder()
                .addStroke(new GestureDescription.StrokeDescription(path, 0, d)).build();
        CountDownLatch latch = new CountDownLatch(1);
        final boolean[] done = {false};
        boolean accepted = dispatchGesture(g, new GestureResultCallback() {
            @Override public void onCompleted(GestureDescription gd) { done[0] = true; latch.countDown(); }
            @Override public void onCancelled(GestureDescription gd) { latch.countDown(); }
        }, new Handler(Looper.getMainLooper()));
        if (!accepted) return fail("GESTURE_NOT_ACCEPTED");
        try { latch.await(2500, TimeUnit.MILLISECONDS); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
        if (!done[0]) return fail("GESTURE_NOT_COMPLETED");
        AccessibilityNodeInfo after = freshApprovedRoot();
        boolean confirmed = after != null && packageName.equals(pkg(after));
        BridgeEvidenceStore.record(this, "SWIPE", confirmed ? "PASS" : "FAIL", "");
        Bundle b = confirmed ? ok() : fail("SWIPE_POSTCONDITION_FAILED");
        if (confirmed) b.putBoolean("confirmed", true);
        return b;
    }

    Bundle globalAction(String name) {
        AccessibilityNodeInfo root = freshApprovedRoot();
        if (root == null) return fail("GLOBAL_ACTION_PRECONDITION_FAILED");
        String n = name == null ? "" : name.trim().toUpperCase(Locale.ROOT);
        int action;
        switch (n) {
            case "BACK": action = GLOBAL_ACTION_BACK; break;
            case "HOME": action = GLOBAL_ACTION_HOME; break;
            case "RECENTS": action = GLOBAL_ACTION_RECENTS; break;
            case "NOTIFICATIONS": action = GLOBAL_ACTION_NOTIFICATIONS; break;
            default: return fail("UNKNOWN_GLOBAL_ACTION");
        }
        boolean dispatched = performGlobalAction(action);
        BridgeEvidenceStore.record(this, "GLOBAL_" + n, dispatched ? "PASS" : "FAIL", "");
        Bundle b = dispatched ? ok() : fail("GLOBAL_ACTION_DISPATCH_FAILED");
        if (dispatched) {
            b.putString("status", "DISPATCH_CONFIRMED");
            b.putBoolean("confirmed", true);
        }
        return b;
    }

    Bundle launchApp(String packageName) {
        if (!BridgeSecurity.WORKER_PACKAGE.equals(packageName)) return fail("PACKAGE_NOT_APPROVED");
        if (!BridgeSecurity.packageInstalled(this, packageName)) {
            return fail("WORKER_NOT_INSTALLED_OR_NOT_VISIBLE");
        }
        if (!BridgeSecurity.signerHistoryContains(this, packageName, BridgeSecurity.WORKER_SIGNER)) {
            Bundle mismatch = fail("WORKER_SIGNER_MISMATCH");
            mismatch.putString("expected_signer", BridgeSecurity.WORKER_SIGNER);
            mismatch.putString("observed_signers", BridgeSecurity.signerDiagnostics(this, packageName));
            return mismatch;
        }
        Intent i = getPackageManager().getLaunchIntentForPackage(packageName);
        if (i == null) return fail("NO_LAUNCH_INTENT");
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        startActivity(i);
        long deadline = SystemClock.elapsedRealtime() + 5000L;
        while (SystemClock.elapsedRealtime() < deadline) {
            if (packageName.equals(activePackage())) {
                BridgeEvidenceStore.record(this, "LAUNCH_APP", "PASS", packageName);
                Bundle b = ok();
                b.putString("status", "TARGET_POSTCONDITION_CONFIRMED");
                b.putBoolean("confirmed", true);
                b.putString("active_package", packageName);
                return b;
            }
            SystemClock.sleep(150L);
        }
        return fail("LAUNCH_POSTCONDITION_FAILED");
    }

    private AccessibilityNodeInfo freshApprovedRoot() {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        return root != null && BridgeSecurity.isPackageApproved(this, pkg(root)) ? root : null;
    }

    private String activePackage() {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        return root == null ? "" : pkg(root);
    }

    private String pkg(AccessibilityNodeInfo root) {
        return root.getPackageName() == null ? "" : root.getPackageName().toString();
    }

    private boolean norm(float v) { return v >= 0f && v <= 1f; }

    private String label(AccessibilityNodeInfo n) {
        if (n.isPassword()) return "[REDACTED_PASSWORD_FIELD]";
        StringBuilder s = new StringBuilder();
        if (n.getText() != null) s.append(n.getText());
        if (n.getContentDescription() != null) s.append(' ').append(n.getContentDescription());
        return s.toString().trim();
    }

    private AccessibilityNodeInfo clickable(AccessibilityNodeInfo n) {
        for (int i = 0; i < 8 && n != null; i++, n = n.getParent()) {
            if (n.isClickable() && n.isEnabled() && n.isVisibleToUser()) return n;
        }
        return null;
    }

    private void collectLabel(AccessibilityNodeInfo n, String wanted, List<AccessibilityNodeInfo> out) {
        if (n == null || out.size() > 8) return;
        if (n.isVisibleToUser() && label(n).equalsIgnoreCase(wanted)) out.add(n);
        for (int i = 0; i < n.getChildCount(); i++) collectLabel(n.getChild(i), wanted, out);
    }

    private void collectEditable(AccessibilityNodeInfo n, List<AccessibilityNodeInfo> out) {
        if (n == null || out.size() > 16) return;
        if (n.isVisibleToUser() && n.isEnabled() && n.isEditable() && !n.isPassword()) out.add(n);
        for (int i = 0; i < n.getChildCount(); i++) collectEditable(n.getChild(i), out);
    }

    private AccessibilityNodeInfo scrollable(AccessibilityNodeInfo root) {
        ArrayDeque<AccessibilityNodeInfo> q = new ArrayDeque<>();
        q.add(root);
        for (int seen = 0; !q.isEmpty() && seen < 400; seen++) {
            AccessibilityNodeInfo n = q.remove();
            if (n.isVisibleToUser() && n.isScrollable()) return n;
            for (int i = 0; i < n.getChildCount(); i++) {
                AccessibilityNodeInfo child = n.getChild(i);
                if (child != null) q.add(child);
            }
        }
        return null;
    }

    private boolean findText(AccessibilityNodeInfo n, String value) {
        if (n == null) return false;
        if (!n.isPassword() && n.getText() != null && value.contentEquals(n.getText())) return true;
        for (int i = 0; i < n.getChildCount(); i++) if (findText(n.getChild(i), value)) return true;
        return false;
    }

    private boolean sensitiveSurface(AccessibilityNodeInfo root) {
        ArrayDeque<AccessibilityNodeInfo> q = new ArrayDeque<>();
        q.add(root);
        int seen = 0;
        while (!q.isEmpty() && seen++ < 400) {
            AccessibilityNodeInfo n = q.remove();
            if (n.isPassword()) return true;
            if ((n.isClickable() || n.isEditable()) && sensitiveLabel(label(n))) return true;
            for (int i = 0; i < n.getChildCount(); i++) {
                AccessibilityNodeInfo c = n.getChild(i);
                if (c != null) q.add(c);
            }
        }
        return false;
    }

    private boolean sensitiveLabel(String label) {
        String x = label == null ? "" : label.toLowerCase(Locale.ROOT);
        String[] denied = {
                "delete account", "hesabı sil", "hesabi sil", "payment", "ödeme", "odeme",
                "card number", "kredi kart", "password", "şifre", "sifre",
                "security settings", "güvenlik ayar", "guvenlik ayar",
                "grant permission", "izin ver", "factory reset", "fabrika ayar"
        };
        for (String d : denied) if (x.contains(d)) return true;
        return false;
    }

    private String snapshot(AccessibilityNodeInfo root) {
        StringBuilder s = new StringBuilder();
        ArrayDeque<AccessibilityNodeInfo> q = new ArrayDeque<>();
        q.add(root);
        for (int seen = 0; !q.isEmpty() && seen < 400; seen++) {
            AccessibilityNodeInfo n = q.remove();
            s.append(n.getClassName()).append('|')
                    .append(n.getViewIdResourceName() == null ? "" : n.getViewIdResourceName()).append('|')
                    .append(label(n)).append('|')
                    .append(n.isClickable()).append('|')
                    .append(n.isEditable()).append('|')
                    .append(n.isScrollable()).append('|')
                    .append(n.isPassword()).append('\n');
            for (int i = 0; i < n.getChildCount(); i++) {
                AccessibilityNodeInfo c = n.getChild(i);
                if (c != null) q.add(c);
            }
        }
        return s.toString();
    }

    private Bundle ok() {
        Bundle b = new Bundle();
        b.putBoolean("ok", true);
        return b;
    }

    private Bundle fail(String reason) {
        BridgeEvidenceStore.record(this, "FAIL", "FAIL", reason);
        Bundle b = new Bundle();
        b.putBoolean("ok", false);
        b.putString("status", "FAILED");
        b.putString("failure", reason);
        return b;
    }
}
