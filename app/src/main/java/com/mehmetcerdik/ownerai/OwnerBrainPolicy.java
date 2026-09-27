package com.mehmetcerdik.ownerai;

import java.util.Locale;

public final class OwnerBrainPolicy {
    private OwnerBrainPolicy() {}

    public static String providerMemoryContext() {
        // Owner memory is private by default. Nothing is exported implicitly.
        return "[]";
    }

    public static boolean isReadOnlyTool(String tool) {
        return "screen_read".equals(tool == null ? "" : tool.trim());
    }

    public static boolean allowTool(String ownerRequest, String tool) {
        String t = tool == null ? "" : tool.trim();
        if (isReadOnlyTool(t)) return true;
        String normalized = normalize(ownerRequest);
        switch (t) {
            case "launch_worker":
                return hasAny(normalized, "aç", "ac", "open", "launch", "افتح");
            case "click_text":
                return hasAny(normalized, "tıkla", "tikla", "dokun", "click", "tap", "اضغط");
            case "type_text":
                return hasAny(normalized, "yaz", "gir", "type", "enter", "اكتب");
            case "swipe":
                return hasAny(normalized, "kaydır", "kaydir", "swipe", "scroll", "اسحب");
            case "back":
                return hasAny(normalized, "geri", "back", "ارجع");
            case "home":
                return normalized.contains(" ana ekran ") || hasAny(normalized, "home");
            case "recents":
                return normalized.contains(" son uygulamalar ") || hasAny(normalized, "recents");
            default:
                return false;
        }
    }

    public static boolean explicitActionIntent(String request) {
        if (request == null) return false;
        String normalized = normalize(request);
        String[] words = {
                "aç", "ac", "tıkla", "tikla", "dokun", "yaz", "gir", "kaydır", "kaydir",
                "geri", "gönder", "gonder", "uygula", "yap", "çalıştır", "calistir",
                "open", "launch", "click", "tap", "type", "enter", "swipe", "scroll",
                "back", "home", "recents", "send", "execute",
                "افتح", "اضغط", "اكتب", "اسحب", "ارجع", "نفذ", "أرسل", "ارسل"
        };
        for (String word : words) {
            if (normalized.contains(" " + word + " ")) return true;
        }
        return false;
    }

    private static String normalize(String request) {
        if (request == null) return " ";
        return " " + request.toLowerCase(Locale.ROOT)
                .replaceAll("[^\\p{L}\\p{N}]+", " ")
                .trim() + " ";
    }

    private static boolean hasAny(String normalized, String... words) {
        for (String word : words) {
            if (normalized.contains(" " + word + " ")) return true;
        }
        return false;
    }
}
