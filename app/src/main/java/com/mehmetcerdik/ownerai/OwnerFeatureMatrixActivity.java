package com.mehmetcerdik.ownerai;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public final class OwnerFeatureMatrixActivity extends Activity {
    private static final String WORKER = "com.codespaceapps.aichat";
    private TextView matrixView;
    private TextView auditView;

    private static final Feature[] FEATURES = new Feature[] {
        new Feature("MODEL_SELECTOR", true, "AUDIT_ONLY", new String[]{"model","gpt","gemini","claude","deepseek","llama","kimi","grok","perplexity"}),
        new Feature("REASONING", true, "AUDIT_ONLY", new String[]{"reasoning","akıl","düşün","thinking","o3"}),
        new Feature("AUTO_ROUTING", true, "OWNER_PROFILE_READY", new String[]{"auto model","otomatik model","auto_model"}),
        new Feature("WEB_SEARCH", true, "OWNER_PROFILE_READY", new String[]{"web search","web araması","web_search"}),
        new Feature("DEEP_RESEARCH", true, "OWNER_PROFILE_READY", new String[]{"deep research","derin araştırma","deep_research"}),
        new Feature("MEMORY", true, "OWNER_PROFILE_READY", new String[]{"memory","hafıza","memories"}),
        new Feature("PERSONALIZATION", true, "OWNER_PROFILE_READY", new String[]{"personalization","kişiselleştirme"}),
        new Feature("CUSTOM_INSTRUCTIONS", true, "OWNER_PROFILE_READY", new String[]{"custom instructions","özel talimat","custom_instructions"}),
        new Feature("VOICE_REALTIME", true, "AUDIT_ONLY", new String[]{"voice","sesli sohbet","realtime","gerçek zaman"}),
        new Feature("MULTIMODAL_INPUT", true, "AUDIT_ONLY", new String[]{"file","dosya","image","görsel","audio","ses","video"}),
        new Feature("OCR", true, "AUDIT_ONLY", new String[]{"ocr","metin tara","scan text"}),
        new Feature("TOOLS", true, "AUDIT_ONLY", new String[]{"tools","araçlar","ai araçları","function"}),
        new Feature("LANGUAGE", true, "AUDIT_ONLY", new String[]{"language","dil","türkçe","english"}),
        new Feature("VOICE_SELECTION", true, "AUDIT_ONLY", new String[]{"voice selection","ses seçimi","voice"}),
        new Feature("DIAGNOSTICS", true, "IMPLEMENTED_LOCAL", new String[]{"diagnostic","tanı","debug","status","durum"}),
        new Feature("OWNER_SECURITY", false, "IMPLEMENTED_LOCAL", new String[]{"owner","bridge","security","güvenlik"})
    };

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int p = (int)(16 * getResources().getDisplayMetrics().density);
        root.setPadding(p,p,p,p);

        TextView title = new TextView(this);
        title.setText("MEHMET OWNER EDITION · FEATURE MATRIX");
        title.setTextSize(20f);
        root.addView(title);

        TextView policy = new TextView(this);
        policy.setText("Public Chatbot AI 3.2.1 salt-okunur baseline'dır. Bu ekran entitlement/paywall/backend değiştirmez; yalnız Owner Edition yerel profilini ve görünür worker UI denetimini yönetir.");
        policy.setPadding(0,12,0,12);
        root.addView(policy);

        Button open = new Button(this);
        open.setText("Chatbot AI 3.2.1'i Aç");
        open.setOnClickListener(v -> {
            Bundle out = BridgeClient.launchApp(this, WORKER);
            auditView.setText("launch=" + bundleSummary(out));
        });
        root.addView(open);

        Button audit = new Button(this);
        audit.setText("Aktif Worker Ekranını Salt-Okunur Denetle");
        audit.setOnClickListener(v -> runAudit());
        root.addView(audit);

        Button refresh = new Button(this);
        refresh.setText("Feature Matrix'i Yenile");
        refresh.setOnClickListener(v -> renderMatrix(null));
        root.addView(refresh);

        matrixView = new TextView(this);
        matrixView.setTextIsSelectable(true);
        matrixView.setPadding(0,16,0,16);
        root.addView(matrixView);

        auditView = new TextView(this);
        auditView.setTextIsSelectable(true);
        root.addView(auditView);

        setContentView(new ScrollView(this) {{ addView(root); }});
        renderMatrix(null);
    }

    private void runAudit() {
        Bundle out = BridgeClient.screenRead(this);
        if (out == null || !out.getBoolean("ok", false)) {
            auditView.setText("AUDIT_BLOCKED: " + bundleSummary(out));
            return;
        }
        String snapshot = out.getString("snapshot", "");
        String normalized = snapshot.toLowerCase(Locale.ROOT);
        JSONObject result = new JSONObject();
        JSONArray observed = new JSONArray();
        try {
            result.put("schema", 1);
            result.put("worker_package", WORKER);
            result.put("mutation", false);
            result.put("bridge_signer_match", BridgeClient.verifyBridge(this));
            for (Feature f : FEATURES) {
                boolean hit = false;
                for (String keyword : f.keywords) {
                    if (normalized.contains(keyword.toLowerCase(Locale.ROOT))) { hit = true; break; }
                }
                JSONObject row = new JSONObject();
                row.put("feature", f.name);
                row.put("baseline_present", f.baselinePresent);
                row.put("owner_edition_status", f.ownerStatus);
                row.put("visible_on_current_screen", hit);
                observed.put(row);
            }
            result.put("features", observed);
            persistAudit(result.toString(2));
            auditView.setText(result.toString(2));
            renderMatrix(observed);
        } catch (Exception e) {
            auditView.setText("AUDIT_ERROR");
        }
    }

    private void renderMatrix(JSONArray observed) {
        StringBuilder sb = new StringBuilder();
        for (int i=0;i<FEATURES.length;i++) {
            Feature f = FEATURES[i];
            String visible = "NOT_AUDITED";
            if (observed != null) {
                JSONObject row = observed.optJSONObject(i);
                if (row != null) visible = String.valueOf(row.optBoolean("visible_on_current_screen", false));
            }
            sb.append(f.name)
              .append(" | BASELINE_PRESENT=").append(f.baselinePresent)
              .append(" | OWNER_EDITION=").append(f.ownerStatus)
              .append(" | CURRENT_SCREEN=").append(visible)
              .append('\n');
        }
        matrixView.setText(sb.toString());
    }

    private void persistAudit(String json) {
        try {
            File dir = new File(getNoBackupFilesDir(), "owner_evidence");
            if (!dir.exists()) dir.mkdirs();
            File file = new File(dir, "feature_matrix_last_audit.json");
            try (FileOutputStream out = new FileOutputStream(file, false)) {
                out.write(json.getBytes(StandardCharsets.UTF_8));
            }
        } catch (Exception ignored) {}
    }

    private static String bundleSummary(Bundle b) {
        if (b == null) return "NULL";
        return "ok=" + b.getBoolean("ok", false) +
            ", status=" + b.getString("status", "") +
            ", failure=" + b.getString("failure", "");
    }

    private static final class Feature {
        final String name;
        final boolean baselinePresent;
        final String ownerStatus;
        final String[] keywords;
        Feature(String name, boolean baselinePresent, String ownerStatus, String[] keywords) {
            this.name = name;
            this.baselinePresent = baselinePresent;
            this.ownerStatus = ownerStatus;
            this.keywords = keywords;
        }
    }
}
