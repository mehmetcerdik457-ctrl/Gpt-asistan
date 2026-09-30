package com.mehmetcerdik.ownerai;

import android.content.Context;
import android.os.Bundle;
import android.os.SystemClock;
import org.json.JSONObject;

public final class OwnerToolBus {
    private static final String WORKER = OwnerBrainPolicy.WORKER_PACKAGE;
    private final Context context;
    private final OwnerMemory memory;

    public OwnerToolBus(Context context, OwnerMemory memory) {
        this.context = context.getApplicationContext();
        this.memory = memory;
    }

    public JSONObject execute(String ownerRequest, String name, JSONObject args) {
        String tool = OwnerBrainPolicy.canonical(name);
        JSONObject safeArgs = args == null ? new JSONObject() : args;

        if (!OwnerSession.isAuthorized(context)) {
            memory.audit("TOOL_POLICY:" + tool, "DENY", "OWNER_SECURE_SESSION_REQUIRED");
            return result(false, "OWNER_SECURE_SESSION_REQUIRED", null);
        }
        if (!BridgeClient.verifyBridge(context)) {
            return result(false, "BRIDGE_SIGNER_MISMATCH_OR_NOT_INSTALLED", null);
        }

        // Read only non-privileged bridge status first. Never arm privileged execution
        // before the current owner request has passed code-level policy authorization.
        Bundle bridgeStatus = BridgeClient.status(context);
        if (bridgeStatus == null || !bridgeStatus.getBoolean("ok", false)) {
            memory.audit("TOOL_POLICY:" + tool, "DENY", "BRIDGE_STATUS_UNAVAILABLE");
            return result(false, "BRIDGE_STATUS_UNAVAILABLE", bridgeStatus);
        }
        String currentPackage = bridgeStatus.getString("active_package", "");

        OwnerBrainPolicy.Decision decision = OwnerBrainPolicy.authorize(
                ownerRequest, tool, safeArgs, currentPackage, OwnerSession.isFresh(context));
        if (!decision.allowed) {
            memory.audit("TOOL_POLICY:" + tool, "DENY", decision.status);
            return result(false, decision.status, null);
        }

        long ttl = Math.min(Math.max(1_000L, OwnerSession.remainingMs()), 120_000L);
        Bundle armed = BridgeClient.arm(context, ttl);
        if (armed == null || !armed.getBoolean("ok", false)) {
            memory.audit("TOOL_POLICY:" + tool, "FAIL", "BRIDGE_ARM_FAILED_AFTER_POLICY");
            return result(false, "BRIDGE_ARM_FAILED", armed);
        }

        Bundle out;
        switch (tool) {
            case "READ_SCREEN": out = BridgeClient.screenRead(context); break;
            case "OPEN_APP": out = BridgeClient.launchApp(context, WORKER); break;
            case "FIND_ELEMENT":
                out = BridgeClient.findElement(context,
                        safeArgs.optString("text", safeArgs.optString("target", "")),
                        safeArgs.optString("role", ""));
                break;
            case "CLICK_ELEMENT":
                out = BridgeClient.clickText(context,
                        safeArgs.optString("target", safeArgs.optString("text", "")));
                break;
            case "TYPE_TEXT":
                out = BridgeClient.typeText(context,
                        safeArgs.optString("selector", ""),
                        safeArgs.optString("text", ""));
                break;
            case "TAP":
                out = BridgeClient.clickText(context, safeArgs.optString("target", ""));
                break;
            case "SWIPE": {
                boolean backward = "backward".equalsIgnoreCase(safeArgs.optString("direction", ""));
                out = BridgeClient.swipe(context,
                        .5f, backward ? .25f : .75f,
                        .5f, backward ? .75f : .25f,
                        400L);
                break;
            }
            case "SCROLL":
                out = BridgeClient.scroll(context,
                        "forward".equalsIgnoreCase(safeArgs.optString("direction", "")));
                break;
            case "BACK": out = BridgeClient.globalAction(context, "BACK"); break;
            case "HOME": out = BridgeClient.globalAction(context, "HOME"); break;
            case "RECENTS": out = BridgeClient.globalAction(context, "RECENTS"); break;
            case "NOTIFICATION_ACTION": out = BridgeClient.globalAction(context, "NOTIFICATIONS"); break;
            case "WAIT_FOR_STATE": return waitForState(safeArgs);
            case "VERIFY_STATE": return verifyState(safeArgs);
            case "SCREENSHOT":
            case "SHARE":
            case "OPEN_FILE":
            case "PICK_FILE":
                return result(false, "TOOL_NOT_IMPLEMENTED_FAIL_CLOSED", null);
            default:
                return result(false, "TOOL_NOT_ALLOWLISTED", null);
        }

        boolean ok = out != null && out.getBoolean("ok", false);
        boolean confirmed = out != null && out.getBoolean("confirmed", ok);
        String failure = out == null ? "NULL_RESULT" : out.getString("failure", "");
        if (ok && isStateChanging(tool) && !confirmed) {
            ok = false;
            failure = "POSTCONDITION_NOT_CONFIRMED";
        }
        memory.audit("TOOL:" + tool, ok ? "PASS" : "FAIL", ok ? "confirmed" : failure);
        JSONObject res = result(ok, ok ? "PASS" : failure, out);

        if (ok && isStateChanging(tool) && !"HOME".equals(tool) && !"RECENTS".equals(tool)
                && !"NOTIFICATION_ACTION".equals(tool)) {
            Bundle after = BridgeClient.screenRead(context);
            try {
                res.put("post_action_observation", bundleJson(after));
                if (after == null || !after.getBoolean("ok", false)) {
                    res.put("ok", false);
                    res.put("status", "POSTCONDITION_REOBSERVE_FAILED");
                }
            } catch (Exception ignored) {}
        }
        return res;
    }

    private JSONObject waitForState(JSONObject args) {
        long timeout = Math.max(250L, Math.min(args.optLong("timeout_ms", 5000L), 10_000L));
        String contains = args.optString("contains", "");
        String differentHash = args.optString("different_from_hash", "");
        long end = SystemClock.elapsedRealtime() + timeout;
        Bundle last = null;
        while (SystemClock.elapsedRealtime() <= end) {
            last = BridgeClient.screenRead(context);
            if (last != null && last.getBoolean("ok", false)) {
                String snapshot = last.getString("snapshot", "");
                String hash = last.getString("snapshot_hash", "");
                boolean contentOk = contains.isEmpty() || snapshot.toLowerCase().contains(contains.toLowerCase());
                boolean hashOk = differentHash.isEmpty() || !differentHash.equals(hash);
                if (contentOk && hashOk) return result(true, "STATE_OBSERVED", last);
            }
            SystemClock.sleep(200L);
        }
        return result(false, "WAIT_FOR_STATE_TIMEOUT", last);
    }

    private JSONObject verifyState(JSONObject args) {
        Bundle now = BridgeClient.screenRead(context);
        if (now == null || !now.getBoolean("ok", false)) return result(false, "STATE_NOT_OBSERVABLE", now);
        String contains = args.optString("contains", "");
        String notHash = args.optString("different_from_hash", "");
        String snapshot = now.getString("snapshot", "");
        String hash = now.getString("snapshot_hash", "");
        boolean ok = (contains.isEmpty() || snapshot.toLowerCase().contains(contains.toLowerCase()))
                && (notHash.isEmpty() || !notHash.equals(hash));
        return result(ok, ok ? "STATE_VERIFIED" : "STATE_MISMATCH", now);
    }

    private static boolean isStateChanging(String tool) { return !OwnerBrainPolicy.isReadOnlyTool(tool); }

    private static JSONObject bundleJson(Bundle bundle) {
        JSONObject b = new JSONObject();
        if (bundle == null) return b;
        try {
            for (String key : bundle.keySet()) {
                Object v = bundle.get(key);
                if (v instanceof String || v instanceof Number || v instanceof Boolean) b.put(key, v);
            }
        } catch (Exception ignored) {}
        return b;
    }

    private static JSONObject result(boolean ok, String status, Bundle bundle) {
        JSONObject o = new JSONObject();
        try {
            o.put("ok", ok);
            o.put("status", status == null ? "" : status);
            if (bundle != null) o.put("bridge", bundleJson(bundle));
        } catch (Exception ignored) {}
        return o;
    }
}
