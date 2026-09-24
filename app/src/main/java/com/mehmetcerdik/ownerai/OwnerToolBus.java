package com.mehmetcerdik.ownerai;

import android.content.Context;
import android.os.Bundle;

import org.json.JSONObject;

public final class OwnerToolBus {
    private static final String WORKER = "com.codespaceapps.aichat";
    private final Context context;
    private final OwnerMemory memory;

    public OwnerToolBus(Context context, OwnerMemory memory) {
        this.context = context.getApplicationContext();
        this.memory = memory;
    }

    public JSONObject execute(String name, JSONObject args) {
        String tool = name == null ? "" : name.trim();
        Bundle out;
        switch (tool) {
            case "screen_read":
                out = BridgeClient.screenRead(context); break;
            case "launch_worker":
                out = BridgeClient.launchApp(context, WORKER); break;
            case "click_text":
                out = BridgeClient.clickText(context, args == null ? "" : args.optString("text", "")); break;
            case "type_text":
                out = BridgeClient.typeText(
                        context,
                        args == null ? "" : args.optString("selector", ""),
                        args == null ? "" : args.optString("text", ""));
                break;
            case "swipe":
                float sx = args == null ? .5f : (float) args.optDouble("sx", .5);
                float sy = args == null ? .75f : (float) args.optDouble("sy", .75);
                float ex = args == null ? .5f : (float) args.optDouble("ex", .5);
                float ey = args == null ? .25f : (float) args.optDouble("ey", .25);
                long ms = args == null ? 400L : args.optLong("duration_ms", 400L);
                out = BridgeClient.swipe(context, sx, sy, ex, ey, ms); break;
            case "back":
                out = BridgeClient.globalAction(context, "BACK"); break;
            case "home":
                out = BridgeClient.globalAction(context, "HOME"); break;
            case "recents":
                out = BridgeClient.globalAction(context, "RECENTS"); break;
            default:
                return result(false, "TOOL_NOT_ALLOWED", null);
        }
        boolean ok = out != null && out.getBoolean("ok", false);
        String failure = out == null ? "NULL_RESULT" : out.getString("failure", "");
        memory.audit("TOOL:" + tool, ok ? "PASS" : "FAIL", ok ? "ok" : failure);
        return result(ok, ok ? "PASS" : failure, out);
    }

    private static JSONObject result(boolean ok, String status, Bundle bundle) {
        JSONObject o = new JSONObject();
        try {
            o.put("ok", ok);
            o.put("status", status == null ? "" : status);
            if (bundle != null) {
                JSONObject b = new JSONObject();
                for (String key : bundle.keySet()) {
                    Object v = bundle.get(key);
                    if (v instanceof String || v instanceof Number || v instanceof Boolean) b.put(key, v);
                }
                o.put("bridge", b);
            }
        } catch (Exception ignored) {}
        return o;
    }
}
