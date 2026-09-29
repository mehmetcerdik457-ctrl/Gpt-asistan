package com.mehmetcerdik.ownerai;

import org.json.JSONArray;
import org.json.JSONObject;

public final class CihatSemanticAdapter {
    public interface Executor {
        JSONObject execute(String ownerRequest, String tool, JSONObject args) throws Exception;
    }

    public enum Step {
        CIHAT_LAUNCH,
        CIHAT_WAIT_READY,
        CIHAT_DETECT_SCREEN,
        CIHAT_FIND_CHAT_INPUT,
        CIHAT_TYPE_PROMPT,
        CIHAT_CAPTURE_TYPED_STATE,
        CIHAT_FIND_SEND,
        CIHAT_SEND,
        CIHAT_WAIT_RESPONSE,
        CIHAT_READ_RESPONSE,
        CIHAT_VERIFY_RESPONSE,
        CIHAT_RECOVER_NAVIGATION
    }

    private final Executor executor;

    public CihatSemanticAdapter(Executor executor) {
        this.executor = executor;
    }

    public JSONObject sendPrompt(String ownerRequest, String prompt) {
        JSONArray trace = new JSONArray();
        try {
            require(step(trace, Step.CIHAT_LAUNCH,
                    executor.execute(ownerRequest, "OPEN_APP",
                            new JSONObject().put("package", OwnerBrainPolicy.WORKER_PACKAGE))));

            require(step(trace, Step.CIHAT_WAIT_READY,
                    executor.execute(ownerRequest, "WAIT_FOR_STATE",
                            new JSONObject().put("timeout_ms", 7000L))));

            JSONObject detected = step(trace, Step.CIHAT_DETECT_SCREEN,
                    executor.execute(ownerRequest, "READ_SCREEN", new JSONObject()));
            require(detected);
            String beforeHash = bridgeString(detected, "snapshot_hash");

            JSONObject input = step(trace, Step.CIHAT_FIND_CHAT_INPUT,
                    executor.execute(ownerRequest, "FIND_ELEMENT",
                            new JSONObject().put("role", "editable")));
            require(input);

            require(step(trace, Step.CIHAT_TYPE_PROMPT,
                    executor.execute(ownerRequest, "TYPE_TEXT",
                            new JSONObject().put("selector", "").put("text", prompt))));

            JSONObject typedState = step(trace, Step.CIHAT_CAPTURE_TYPED_STATE,
                    executor.execute(ownerRequest, "READ_SCREEN", new JSONObject()));
            require(typedState);
            String typedHash = bridgeString(typedState, "snapshot_hash");
            if (typedHash.isEmpty()) return fail(trace, "CIHAT_TYPED_STATE_HASH_MISSING");
            if (!beforeHash.isEmpty() && beforeHash.equals(typedHash)) {
                return fail(trace, "CIHAT_TYPE_POSTCONDITION_NOT_OBSERVED");
            }

            String sendLabel = findSend(ownerRequest, trace);
            if (sendLabel == null) return fail(trace, "CIHAT_SEND_CONTROL_NOT_FOUND");

            require(step(trace, Step.CIHAT_SEND,
                    executor.execute(ownerRequest, "CLICK_ELEMENT",
                            new JSONObject().put("target", sendLabel))));

            JSONObject waitArgs = new JSONObject().put("timeout_ms", 10_000L)
                    .put("different_from_hash", typedHash);
            require(step(trace, Step.CIHAT_WAIT_RESPONSE,
                    executor.execute(ownerRequest, "WAIT_FOR_STATE", waitArgs)));

            JSONObject response = step(trace, Step.CIHAT_READ_RESPONSE,
                    executor.execute(ownerRequest, "READ_SCREEN", new JSONObject()));
            require(response);

            JSONObject verifyArgs = new JSONObject()
                    .put("different_from_hash", typedHash);
            require(step(trace, Step.CIHAT_VERIFY_RESPONSE,
                    executor.execute(ownerRequest, "VERIFY_STATE", verifyArgs)));

            return new JSONObject()
                    .put("ok", true)
                    .put("status", "CIHAT_SEMANTIC_ADAPTER_VERIFIED")
                    .put("trace", trace)
                    .put("screen", response);
        } catch (Exception e) {
            return fail(trace, "CIHAT_ADAPTER_FAIL_CLOSED:" + e.getClass().getSimpleName());
        }
    }

    private String findSend(String ownerRequest, JSONArray trace) throws Exception {
        for (String label : new String[]{"Gönder", "Gonder", "Send", "Send message"}) {
            JSONObject found = step(trace, Step.CIHAT_FIND_SEND,
                    executor.execute(ownerRequest, "FIND_ELEMENT", new JSONObject().put("text", label)));
            if (found.optBoolean("ok", false)) return label;
        }
        return null;
    }

    private static JSONObject step(JSONArray trace, Step step, JSONObject result) throws Exception {
        JSONObject safe = result == null
                ? new JSONObject().put("ok", false).put("status", "NULL_RESULT")
                : result;
        trace.put(new JSONObject().put("step", step.name()).put("result", safe));
        return safe;
    }

    private static void require(JSONObject result) {
        if (result == null || !result.optBoolean("ok", false)) {
            throw new IllegalStateException(result == null ? "NULL" : result.optString("status", "STEP_FAILED"));
        }
    }

    private static String bridgeString(JSONObject result, String key) {
        JSONObject bridge = result == null ? null : result.optJSONObject("bridge");
        return bridge == null ? "" : bridge.optString(key, "");
    }

    private static JSONObject fail(JSONArray trace, String status) {
        JSONObject o = new JSONObject();
        try {
            o.put("ok", false);
            o.put("status", status);
            o.put("trace", trace);
            o.put("recovery", Step.CIHAT_RECOVER_NAVIGATION.name() + ":REOBSERVE_REQUIRED");
        } catch (Exception ignored) {}
        return o;
    }
}
