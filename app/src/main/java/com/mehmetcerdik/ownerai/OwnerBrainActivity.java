package com.mehmetcerdik.ownerai;

import android.app.Activity;
import android.os.Bundle;
import android.text.InputType;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class OwnerBrainActivity extends Activity {
    private OwnerBrainEngine engine;
    private EditText endpoint;
    private EditText model;
    private EditText secret;
    private EditText prompt;
    private TextView output;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        engine = new OwnerBrainEngine(this);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int p = (int)(16 * getResources().getDisplayMetrics().density);
        root.setPadding(p,p,p,p);

        TextView title = new TextView(this);
        title.setText("MEHMET AI — OWNER BRAIN");
        title.setTextSize(22f);
        root.addView(title);

        TextView note = new TextView(this);
        note.setText("Beyin + Memory + Model Provider + ToolBus. API anahtarı Android Keystore ile cihazda şifreli tutulur; repo/log içine yazılmaz.");
        root.addView(note);

        endpoint = field("Provider endpoint", "https://api.openai.com/v1/responses");
        model = field("Model adı", "");
        secret = field("API anahtarı (bir kez gir)", "");
        secret.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        prompt = field("Mehmet AI'ya görev ver", "");

        root.addView(endpoint); root.addView(model); root.addView(secret); root.addView(prompt);

        Button save = new Button(this); save.setText("Provider Ayarlarını Güvenli Kaydet");
        save.setOnClickListener(v -> {
            engine.saveConfig(endpoint.getText().toString(), model.getText().toString(), secret.getText().toString());
            secret.setText("");
            output.setText(engine.status().toString());
        });
        root.addView(save);

        Button run = new Button(this); run.setText("Beyne Sor / Planla / Gerekirse Tool Çalıştır");
        run.setOnClickListener(v -> runBrain());
        root.addView(run);

        Button mem = new Button(this); mem.setText("Owner Memory Göster");
        mem.setOnClickListener(v -> output.setText(engine.memorySnapshot().toString()));
        root.addView(mem);

        Button audit = new Button(this); audit.setText("Audit Göster");
        audit.setOnClickListener(v -> output.setText(engine.auditSnapshot().toString()));
        root.addView(audit);

        output = new TextView(this);
        output.setTextIsSelectable(true);
        output.setText(engine.status().toString());
        root.addView(output, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        ScrollView s = new ScrollView(this); s.addView(root); setContentView(s);
    }

    private EditText field(String hint, String value) {
        EditText e = new EditText(this); e.setHint(hint); e.setText(value); return e;
    }

    private void runBrain() {
        final String text = prompt.getText().toString();
        output.setText("Çalışıyor…");
        executor.submit(() -> {
            JSONObject result = engine.run(text);
            runOnUiThread(() -> output.setText(result.toString()));
        });
    }

    @Override protected void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }
}
