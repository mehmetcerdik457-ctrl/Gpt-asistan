package com.mehmetcerdik.ownerai;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONObject;

import java.util.Locale;

public final class OwnerFeatureConfig {
    private static final String PREFS = "owner_brain_config";
    private final SharedPreferences prefs;

    public OwnerFeatureConfig(Context context) {
        prefs = context.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public void save(
            String selectedModel,
            String fastModel,
            String reasoningModel,
            String deepResearchModel,
            boolean autoRouting,
            String reasoningEffort,
            boolean webSearch,
            boolean deepResearch,
            boolean shareMemory,
            String customInstructions,
            String personalization,
            String language,
            String voice
    ) {
        prefs.edit()
                .putString("model", clean(selectedModel))
                .putString("fast_model", clean(fastModel))
                .putString("reasoning_model", clean(reasoningModel))
                .putString("deep_research_model", clean(deepResearchModel))
                .putBoolean("auto_routing", autoRouting)
                .putString("reasoning_effort", normalizeReasoningEffort(reasoningEffort))
                .putBoolean("web_search", webSearch)
                .putBoolean("deep_research", deepResearch)
                .putBoolean("share_memory", shareMemory)
                .putString("custom_instructions", bounded(customInstructions, 12000))
                .putString("personalization", bounded(personalization, 8000))
                .putString("language", bounded(language, 120))
                .putString("voice", bounded(voice, 120))
                .apply();
    }

    public String selectedModel() { return prefs.getString("model", ""); }
    public String fastModel() { return prefs.getString("fast_model", ""); }
    public String reasoningModel() { return prefs.getString("reasoning_model", ""); }
    public String deepResearchModel() { return prefs.getString("deep_research_model", ""); }
    public boolean autoRouting() { return prefs.getBoolean("auto_routing", false); }
    public String reasoningEffort() { return normalizeReasoningEffort(prefs.getString("reasoning_effort", "provider_default")); }
    public boolean webSearch() { return prefs.getBoolean("web_search", false); }
    public boolean deepResearch() { return prefs.getBoolean("deep_research", false); }
    public boolean shareMemory() { return prefs.getBoolean("share_memory", false); }
    public String customInstructions() { return prefs.getString("custom_instructions", ""); }
    public String personalization() { return prefs.getString("personalization", ""); }
    public String language() { return prefs.getString("language", ""); }
    public String voice() { return prefs.getString("voice", ""); }

    public String chooseModel(String input) {
        return routeModel(
                autoRouting(),
                deepResearch(),
                selectedModel(),
                fastModel(),
                reasoningModel(),
                deepResearchModel(),
                input
        );
    }

    public String ownerContext() {
        StringBuilder b = new StringBuilder();
        append(b, "PREFERRED_LANGUAGE", language());
        append(b, "PERSONALIZATION", personalization());
        append(b, "CUSTOM_INSTRUCTIONS", customInstructions());
        append(b, "VOICE_PREFERENCE", voice());
        if (deepResearch()) {
            b.append("\nDEEP_RESEARCH_MODE=ENABLED; verify claims, prefer primary sources, and state uncertainty.");
        }
        return b.toString();
    }

    public JSONObject snapshot() {
        JSONObject o = new JSONObject();
        try {
            o.put("selected_model", selectedModel());
            o.put("fast_model", fastModel());
            o.put("reasoning_model", reasoningModel());
            o.put("deep_research_model", deepResearchModel());
            o.put("auto_routing", autoRouting());
            o.put("reasoning_effort", reasoningEffort());
            o.put("web_search", webSearch());
            o.put("deep_research", deepResearch());
            o.put("share_memory_with_provider", shareMemory());
            o.put("custom_instructions_configured", !customInstructions().isEmpty());
            o.put("personalization_configured", !personalization().isEmpty());
            o.put("language", language());
            o.put("voice", voice());
            o.put("video_input", "BOUNDED_SAMPLED_FRAMES_SOURCE_IMPLEMENTED_NOT_RUNTIME_VERIFIED");
            o.put("realtime_voice", "WEBRTC_EPHEMERAL_TOKEN_SOURCE_IMPLEMENTED_NOT_RUNTIME_VERIFIED");
        } catch (Exception ignored) {}
        return o;
    }

    public static String routeModel(
            boolean autoRouting,
            boolean deepResearch,
            String selected,
            String fast,
            String reasoning,
            String deep,
            String input
    ) {
        String selectedClean = clean(selected);
        if (deepResearch && !clean(deep).isEmpty()) return clean(deep);
        if (!autoRouting) return selectedClean;
        if (looksReasoningHeavy(input) && !clean(reasoning).isEmpty()) return clean(reasoning);
        if (!clean(fast).isEmpty()) return clean(fast);
        if (!clean(reasoning).isEmpty()) return clean(reasoning);
        return selectedClean;
    }

    public static boolean looksReasoningHeavy(String input) {
        String x = input == null ? "" : input.toLowerCase(Locale.ROOT);
        String[] markers = {
                "neden", "niçin", "analiz", "karşılaştır", "kanıt", "ispat", "hesapla", "kod", "debug",
                "why", "analyze", "compare", "prove", "reason", "calculate", "code", "debug",
                "حلل", "قارن", "لماذا", "احسب"
        };
        for (String marker : markers) if (x.contains(marker)) return true;
        return x.length() > 1200;
    }

    public static String normalizeReasoningEffort(String value) {
        String x = clean(value).toLowerCase(Locale.ROOT);
        switch (x) {
            case "none":
            case "minimal":
            case "low":
            case "medium":
            case "high":
            case "xhigh":
                return x;
            default:
                return "provider_default";
        }
    }

    private static void append(StringBuilder b, String key, String value) {
        String clean = value == null ? "" : value.trim();
        if (!clean.isEmpty()) b.append("\n").append(key).append("=").append(clean);
    }

    private static String bounded(String value, int max) {
        String x = clean(value);
        return x.length() <= max ? x : x.substring(0, max);
    }

    private static String clean(String value) {
        return value == null ? "" : value.trim();
    }
}
