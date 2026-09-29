package com.mehmetcerdik.ownerai;

import android.app.Activity;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.speech.RecognizerIntent;
import android.speech.tts.TextToSpeech;
import android.text.InputType;
import android.util.Base64;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class OwnerBrainActivity extends AppCompatActivity {
    private static final int PICK_ATTACHMENT = 2401;
    private static final int PICK_SPEECH = 2402;
    private static final int MAX_ATTACHMENT_BYTES = 12 * 1024 * 1024;

    private OwnerBrainEngine engine;
    private EditText endpoint;
    private EditText model;
    private EditText fastModel;
    private EditText reasoningModel;
    private EditText deepModel;
    private EditText secret;
    private EditText customInstructions;
    private EditText personalization;
    private EditText language;
    private EditText voice;
    private EditText prompt;
    private CheckBox autoRouting;
    private CheckBox webSearch;
    private CheckBox deepResearch;
    private CheckBox shareMemory;
    private Spinner reasoningEffort;
    private TextView attachmentStatus;
    private TextView output;
    private OwnerAttachment attachment;
    private TextToSpeech tts;
    private String lastReply = "";
    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        engine = new OwnerBrainEngine(this);
        tts = new TextToSpeech(this, status -> {
            if (status == TextToSpeech.SUCCESS) configureTts();
        });
        JSONObject initial = engine.status();
        JSONObject feature = initial.optJSONObject("features");
        if (feature == null) feature = new JSONObject();

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int p = (int)(16 * getResources().getDisplayMetrics().density);
        root.setPadding(p,p,p,p);

        TextView title = new TextView(this);
        title.setText("MEHMET AI — OWNER BRAIN / FEATURE PARITY");
        title.setTextSize(22f);
        root.addView(title);

        TextView note = new TextView(this);
        note.setText("Public CİHAT worker değişmez. Owner ayarları bu ayrı uygulamada tutulur. API anahtarı Android Keystore ile şifrelenir; kalıcı memory provider'a yalnız açık opt-in ile gönderilir.");
        root.addView(note);

        endpoint = field("Provider endpoint (production canonical, read-only)", ProviderEndpointPolicy.CANONICAL);
        endpoint.setEnabled(false);
        endpoint.setFocusable(false);
        model = field("Seçili / varsayılan model", feature.optString("selected_model", ""));
        fastModel = field("Auto-route hızlı model slotu", feature.optString("fast_model", ""));
        reasoningModel = field("Auto-route reasoning model slotu", feature.optString("reasoning_model", ""));
        deepModel = field("Deep-research model slotu", feature.optString("deep_research_model", ""));
        secret = field("API anahtarı (yalnız değiştirirken gir)", "");
        secret.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);

        autoRouting = check("Auto model routing", feature.optBoolean("auto_routing", false));
        webSearch = check("Web search", feature.optBoolean("web_search", false));
        deepResearch = check("Deep research mode", feature.optBoolean("deep_research", false));
        shareMemory = check("Owner memory'yi provider contextine açıkça dahil et", feature.optBoolean("share_memory_with_provider", false));

        customInstructions = field("Custom instructions", "");
        personalization = field("Personalization / tercih edilen cevap stili", "");
        language = field("Tercih edilen dil", feature.optString("language", ""));
        voice = field("Voice tercihi (ayar; realtime henüz kapalı)", feature.optString("voice", ""));

        String[] efforts = {"provider_default", "none", "minimal", "low", "medium", "high", "xhigh"};
        reasoningEffort = new Spinner(this);
        reasoningEffort.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, efforts));
        String currentEffort = feature.optString("reasoning_effort", "provider_default");
        for (int i = 0; i < efforts.length; i++) if (efforts[i].equals(currentEffort)) reasoningEffort.setSelection(i);

        prompt = field("Mehmet AI'ya görev ver", "");

        root.addView(endpoint); root.addView(model); root.addView(fastModel); root.addView(reasoningModel); root.addView(deepModel);
        root.addView(autoRouting); root.addView(reasoningEffort); root.addView(webSearch); root.addView(deepResearch); root.addView(shareMemory);
        root.addView(customInstructions); root.addView(personalization); root.addView(language); root.addView(voice);
        root.addView(secret);

        Button save = new Button(this); save.setText("Owner Ayarlarını Güvenli Kaydet");
        save.setOnClickListener(v -> OwnerAuth.requireFresh(this, () -> {
            engine.saveConfig(endpoint.getText().toString(), model.getText().toString(), secret.getText().toString());
            engine.saveFeatures(
                    model.getText().toString(),
                    fastModel.getText().toString(),
                    reasoningModel.getText().toString(),
                    deepModel.getText().toString(),
                    autoRouting.isChecked(),
                    String.valueOf(reasoningEffort.getSelectedItem()),
                    webSearch.isChecked(),
                    deepResearch.isChecked(),
                    shareMemory.isChecked(),
                    customInstructions.getText().toString(),
                    personalization.getText().toString(),
                    language.getText().toString(),
                    voice.getText().toString()
            );
            secret.setText("");
            output.setText(engine.status().toString());
        }, s -> output.setText(s)));
        root.addView(save);

        attachmentStatus = new TextView(this);
        attachmentStatus.setText("Attachment: NONE");
        root.addView(attachmentStatus);

        Button attach = new Button(this); attach.setText("Görsel / PDF / Dosya / MP3-WAV Seç");
        attach.setOnClickListener(v -> OwnerAuth.require(this, this::openAttachmentPicker, s -> output.setText(s)));
        root.addView(attach);

        Button clearAttachment = new Button(this); clearAttachment.setText("Attachment Temizle");
        clearAttachment.setOnClickListener(v -> {
            attachment = null;
            attachmentStatus.setText("Attachment: NONE");
        });
        root.addView(clearAttachment);

        root.addView(prompt);

        Button speech = new Button(this); speech.setText("Konuşarak Görev Gir");
        speech.setOnClickListener(v -> OwnerAuth.require(this, this::startSpeechInput, s -> output.setText(s)));
        root.addView(speech);

        Button run = new Button(this); run.setText("Beyne Sor / Planla / Gerekirse Tool Çalıştır");
        run.setOnClickListener(v -> requireForRequest(prompt.getText().toString(), () -> runBrain(prompt.getText().toString())));
        root.addView(run);

        Button speak = new Button(this); speak.setText("Son Cevabı Seslendir");
        speak.setOnClickListener(v -> OwnerAuth.require(this, this::speakLastReply, s -> output.setText(s)));
        root.addView(speak);

        Button ocr = new Button(this); ocr.setText("Seçili Görselden OCR");
        ocr.setOnClickListener(v -> OwnerAuth.require(this, () -> {
            if (attachment == null || attachment.kind != OwnerAttachment.Kind.IMAGE) {
                output.setText("OCR_REQUIRES_EXPLICIT_IMAGE_ATTACHMENT");
                return;
            }
            runBrain("Extract all visible text from the attached image faithfully. Preserve line breaks where useful. Do not invent unreadable text.");
        }, s -> output.setText(s)));
        root.addView(ocr);

        Button mem = new Button(this); mem.setText("Owner Memory Göster");
        mem.setOnClickListener(v -> OwnerAuth.require(this,
                () -> output.setText(engine.memorySnapshot().toString()),
                s -> output.setText(s)));
        root.addView(mem);

        Button audit = new Button(this); audit.setText("Audit Göster");
        audit.setOnClickListener(v -> OwnerAuth.require(this,
                () -> output.setText(engine.auditSnapshot().toString()),
                s -> output.setText(s)));
        root.addView(audit);

        Button diagnostics = new Button(this); diagnostics.setText("Diagnostics / Capability Durumu");
        diagnostics.setOnClickListener(v -> OwnerAuth.require(this, () -> {
            JSONObject s = engine.status();
            try {
                s.put("attachment", attachment == null ? "NONE" : attachment.metadata());
                s.put("public_worker_package", "com.codespaceapps.aichat");
                s.put("public_worker_mutation", "FORBIDDEN");
            } catch (Exception ignored) {}
            output.setText(s.toString());
        }, s -> output.setText(s)));
        root.addView(diagnostics);

        output = new TextView(this);
        output.setTextIsSelectable(true);
        output.setText("OWNER_AUTH_REQUIRED");
        root.addView(output, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        ScrollView s = new ScrollView(this); s.addView(root); setContentView(s);
    }

    private EditText field(String hint, String value) {
        EditText e = new EditText(this); e.setHint(hint); e.setText(value); return e;
    }

    private CheckBox check(String label, boolean checked) {
        CheckBox b = new CheckBox(this); b.setText(label); b.setChecked(checked); return b;
    }

    private void openAttachmentPicker() {
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.setType("*/*");
        i.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{
                "image/*", "application/pdf", "text/*", "application/json",
                "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "video/*"
        });
        startActivityForResult(i, PICK_ATTACHMENT);
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (resultCode != Activity.RESULT_OK || data == null) return;
        if (requestCode == PICK_SPEECH) {
            ArrayList<String> results = data.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS);
            if (results != null && !results.isEmpty()) {
                prompt.setText(results.get(0));
                output.setText("VOICE_INPUT_CAPTURED");
            }
            return;
        }
        if (requestCode == PICK_ATTACHMENT && data.getData() != null) {
            Uri uri = data.getData();
            OwnerAuth.require(this, () -> loadAttachment(uri), s -> output.setText(s));
        }
    }

    private void loadAttachment(Uri uri) {
        try {
            String mime = getContentResolver().getType(uri);
            if (mime == null) mime = "application/octet-stream";
            String name = displayName(uri);
            if (mime.startsWith("video/")) {
                attachment = VideoPipeline.sampleToImage(getContentResolver(), uri, name);
                attachmentStatus.setText("Attachment: VIDEO_SAMPLED_FRAMES · " + name);
                output.setText("VIDEO_PIPELINE_SAMPLED_FRAMES_SOURCE_IMPLEMENTED_NOT_RUNTIME_VERIFIED");
                return;
            }

            byte[] bytes = readBounded(uri);
            String encoded = Base64.encodeToString(bytes, Base64.NO_WRAP);
            OwnerAttachment.Kind kind;
            if (mime.startsWith("image/")) {
                kind = OwnerAttachment.Kind.IMAGE;
            } else if (isSupportedAudio(mime, name)) {
                kind = OwnerAttachment.Kind.AUDIO;
            } else {
                kind = OwnerAttachment.Kind.FILE;
            }
            attachment = new OwnerAttachment(kind, mime, name, encoded);
            attachmentStatus.setText("Attachment: " + kind + " · " + name + " · " + bytes.length + " bytes");
            output.setText(attachment.metadata().toString());
        } catch (Exception e) {
            attachment = null;
            attachmentStatus.setText("Attachment: LOAD_FAILED");
            output.setText("ATTACHMENT_LOAD_FAILED:" + e.getClass().getSimpleName());
        }
    }

    private byte[] readBounded(Uri uri) throws Exception {
        try (InputStream in = getContentResolver().openInputStream(uri);
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            if (in == null) throw new IllegalStateException("NO_INPUT_STREAM");
            byte[] buffer = new byte[64 * 1024];
            int total = 0;
            for (int n; (n = in.read(buffer)) >= 0;) {
                total += n;
                if (total > MAX_ATTACHMENT_BYTES) throw new IllegalStateException("ATTACHMENT_TOO_LARGE");
                out.write(buffer, 0, n);
            }
            return out.toByteArray();
        }
    }

    private String displayName(Uri uri) {
        try (Cursor c = getContentResolver().query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (c != null && c.moveToFirst()) {
                int ix = c.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (ix >= 0) return c.getString(ix);
            }
        } catch (Exception ignored) {}
        return "owner-input";
    }

    private boolean isSupportedAudio(String mime, String name) {
        String m = mime == null ? "" : mime.toLowerCase(java.util.Locale.ROOT);
        String n = name == null ? "" : name.toLowerCase(java.util.Locale.ROOT);
        return m.contains("mpeg") || m.contains("mp3") || m.contains("wav") || n.endsWith(".mp3") || n.endsWith(".wav");
    }

    private void startSpeechInput() {
        try {
            Intent i = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
            i.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
            String tag = language.getText().toString().trim();
            if (!tag.isEmpty()) i.putExtra(RecognizerIntent.EXTRA_LANGUAGE, tag);
            i.putExtra(RecognizerIntent.EXTRA_PROMPT, "MEHMET AI için konuş");
            startActivityForResult(i, PICK_SPEECH);
        } catch (Exception e) {
            output.setText("VOICE_INPUT_UNAVAILABLE:" + e.getClass().getSimpleName());
        }
    }

    private void configureTts() {
        if (tts == null) return;
        String tag = language == null ? "" : language.getText().toString().trim();
        if (!tag.isEmpty()) {
            try { tts.setLanguage(Locale.forLanguageTag(tag)); } catch (Exception ignored) {}
        }
        String requested = voice == null ? "" : voice.getText().toString().trim();
        if (!requested.isEmpty()) {
            try {
                Set<android.speech.tts.Voice> voices = tts.getVoices();
                if (voices != null) {
                    for (android.speech.tts.Voice candidate : voices) {
                        if (requested.equalsIgnoreCase(candidate.getName())) {
                            tts.setVoice(candidate);
                            break;
                        }
                    }
                }
            } catch (Exception ignored) {}
        }
    }

    private void speakLastReply() {
        if (lastReply == null || lastReply.trim().isEmpty()) {
            output.setText("VOICE_OUTPUT_NO_REPLY");
            return;
        }
        configureTts();
        if (tts == null) {
            output.setText("VOICE_OUTPUT_UNAVAILABLE");
            return;
        }
        int result = tts.speak(lastReply, TextToSpeech.QUEUE_FLUSH, null, "owner-reply");
        output.setText(result == TextToSpeech.SUCCESS ? "VOICE_OUTPUT_STARTED" : "VOICE_OUTPUT_FAILED:" + result);
    }

    private void requireForRequest(String request, Runnable action) {
        if (OwnerBrainPolicy.isHighRisk(request)) {
            OwnerAuth.requireFresh(this, action, status -> output.setText(status));
        } else {
            OwnerAuth.require(this, action, status -> output.setText(status));
        }
    }

    private void runBrain(String text) {
        output.setText("Çalışıyor…");
        final OwnerAttachment current = attachment;
        executor.submit(() -> {
            JSONObject result = engine.run(text, current);
            String reply = result.optString("reply", "");
            runOnUiThread(() -> {
                lastReply = reply;
                output.setText(result.toString());
            });
        });
    }

    @Override protected void onDestroy() {
        executor.shutdownNow();
        if (tts != null) {
            tts.stop();
            tts.shutdown();
        }
        super.onDestroy();
    }
}
