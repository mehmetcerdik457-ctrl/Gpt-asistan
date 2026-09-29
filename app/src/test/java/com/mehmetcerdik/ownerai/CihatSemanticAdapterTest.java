package com.mehmetcerdik.ownerai;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.Assert.*;

public final class CihatSemanticAdapterTest {
    @Test public void deterministicHappyPathIncludesMandatoryPostconditions() throws Exception {
        List<String> calls = new ArrayList<>();
        final int[] reads = {0};
        CihatSemanticAdapter adapter = new CihatSemanticAdapter((owner, tool, args) -> {
            calls.add(tool);
            JSONObject out = new JSONObject().put("ok", true).put("status", "PASS");
            if ("READ_SCREEN".equals(tool)) {
                reads[0]++;
                out.put("bridge", new JSONObject()
                        .put("snapshot_hash", reads[0] == 1 ? "before" : "after")
                        .put("snapshot", "chat state " + reads[0]));
            }
            if ("FIND_ELEMENT".equals(tool)) out.put("bridge", new JSONObject().put("exists", true));
            return out;
        });

        JSONObject out = adapter.sendPrompt("CİHAT'a merhaba yaz ve gönder", "merhaba");
        assertTrue(out.toString(), out.optBoolean("ok", false));
        assertTrue(calls.contains("OPEN_APP"));
        assertTrue(calls.contains("FIND_ELEMENT"));
        assertTrue(calls.contains("TYPE_TEXT"));
        assertTrue(calls.contains("CLICK_ELEMENT"));
        assertTrue(calls.contains("WAIT_FOR_STATE"));
        assertTrue(calls.contains("VERIFY_STATE"));

        JSONArray trace = out.optJSONArray("trace");
        assertNotNull(trace);
        assertTrue(trace.length() >= 9);
    }

    @Test public void failedStepFailsClosed() throws Exception {
        CihatSemanticAdapter adapter = new CihatSemanticAdapter((owner, tool, args) ->
                new JSONObject().put("ok", !"FIND_ELEMENT".equals(tool)).put("status", "TEST"));
        JSONObject out = adapter.sendPrompt("CİHAT'a merhaba yaz ve gönder", "merhaba");
        assertFalse(out.optBoolean("ok", true));
        assertTrue(out.optString("status").startsWith("CIHAT_ADAPTER_FAIL_CLOSED")
                || out.optString("status").equals("CIHAT_SEND_CONTROL_NOT_FOUND"));
    }
}
