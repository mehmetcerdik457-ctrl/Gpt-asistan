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
        if (isReadOnlyTool(tool)) return true;
        return explicitActionIntent(ownerRequest);
    }

    public static boolean explicitActionIntent(String request) {
        if (request == null) return false;
        String normalized = " " + request.toLowerCase(Locale.ROOT)
                .replaceAll("[^\\p{L}\\p{N}]+", " ")
                .trim() + " ";
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
}
