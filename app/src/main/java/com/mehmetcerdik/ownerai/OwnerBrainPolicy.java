package com.mehmetcerdik.ownerai;

import org.json.JSONObject;
import java.util.Locale;

public final class OwnerBrainPolicy {
    public static final String WORKER_PACKAGE = "com.codespaceapps.aichat";
    public static final String OWNER_PACKAGE = "com.mehmetcerdik.ownerai";

    public static final class Decision {
        public final boolean allowed;
        public final String status;
        Decision(boolean allowed, String status) { this.allowed = allowed; this.status = status; }
        static Decision allow() { return new Decision(true, "ALLOW"); }
        static Decision deny(String status) { return new Decision(false, status); }
    }

    private OwnerBrainPolicy() {}
    public static String providerMemoryContext() { return "[]"; }

    public static boolean isReadOnlyTool(String tool) {
        String t = canonical(tool);
        return "READ_SCREEN".equals(t) || "FIND_ELEMENT".equals(t)
                || "WAIT_FOR_STATE".equals(t) || "VERIFY_STATE".equals(t);
    }

    public static boolean isHighRisk(String request) {
        String n = normalize(request);
        return hasAny(n, "hesabı sil", "hesabi sil", "delete account",
                "ödeme", "odeme", "payment", "para gönder", "para gonder",
                "şifre", "sifre", "password", "izin ver", "permission",
                "güvenlik ayarı", "guvenlik ayari", "security setting",
                "fabrika ayarı", "fabrika ayari", "factory reset",
                "satın al", "satin al", "purchase", "subscribe");
    }

    public static Decision authorize(String ownerRequest, String tool, JSONObject args,
                                     String currentPackage, boolean freshOwnerAuth) {
        String t = canonical(tool);
        JSONObject a = args == null ? new JSONObject() : args;
        String request = normalize(ownerRequest);

        if (isReadOnlyTool(t)) return Decision.allow();
        if (isHighRisk(ownerRequest) && !freshOwnerAuth) return Decision.deny("FRESH_OWNER_AUTH_REQUIRED");

        switch (t) {
            case "OPEN_APP": {
                if (!hasAny(request, "aç", "ac", "open", "launch", "başlat", "baslat", "افتح"))
                    return Decision.deny("OWNER_ACTION_VERB_REQUIRED");
                String pkg = a.optString("package", WORKER_PACKAGE);
                if (!WORKER_PACKAGE.equals(pkg)) return Decision.deny("PACKAGE_TARGET_DENIED");
                return mentionsWorker(request) ? Decision.allow() : Decision.deny("WORKER_TARGET_NOT_IN_OWNER_INTENT");
            }
            case "CLICK_ELEMENT": {
                if (!WORKER_PACKAGE.equals(currentPackage)) return Decision.deny("FOREGROUND_PACKAGE_DENIED");
                if (!hasAny(request, "tıkla", "tikla", "dokun", "click", "tap", "bas", "gönder", "gonder", "send", "sor", "اضغط", "أرسل", "ارسل"))
                    return Decision.deny("OWNER_ACTION_VERB_REQUIRED");
                String target = firstNonEmpty(a.optString("target", ""), a.optString("text", ""));
                if (target.isEmpty()) return Decision.deny("ACTION_TARGET_REQUIRED");
                if (requestContainsTarget(request, target)) return Decision.allow();
                if (isSendTarget(target) && mentionsWorker(request)
                        && hasAny(request, "gönder", "gonder", "send", "sor", "yaz", "mesaj", "أرسل", "ارسل"))
                    return Decision.allow();
                return Decision.deny("ACTION_TARGET_NOT_BOUND_TO_OWNER_INTENT");
            }
            case "TYPE_TEXT": {
                if (!WORKER_PACKAGE.equals(currentPackage)) return Decision.deny("FOREGROUND_PACKAGE_DENIED");
                if (!hasAny(request, "yaz", "gir", "type", "enter", "sor", "mesaj", "اكتب"))
                    return Decision.deny("OWNER_ACTION_VERB_REQUIRED");
                String value = a.optString("text", "").trim();
                if (value.isEmpty()) return Decision.deny("TYPE_VALUE_REQUIRED");
                if (!requestContainsTarget(request, value)) return Decision.deny("TYPE_VALUE_NOT_BOUND_TO_OWNER_INTENT");
                String selector = a.optString("selector", "").trim();
                if (!selector.isEmpty() && !requestContainsTarget(request, selector))
                    return Decision.deny("TYPE_SELECTOR_NOT_BOUND_TO_OWNER_INTENT");
                return Decision.allow();
            }
            case "TAP": {
                if (!WORKER_PACKAGE.equals(currentPackage)) return Decision.deny("FOREGROUND_PACKAGE_DENIED");
                String target = a.optString("target", "").trim();
                return !target.isEmpty() && requestContainsTarget(request, target)
                        ? Decision.allow() : Decision.deny("SEMANTIC_TAP_TARGET_REQUIRED");
            }
            case "SWIPE":
            case "SCROLL":
                if (!WORKER_PACKAGE.equals(currentPackage)) return Decision.deny("FOREGROUND_PACKAGE_DENIED");
                return hasAny(request, "kaydır", "kaydir", "swipe", "scroll", "aşağı", "asagi", "yukarı", "yukari", "اسحب")
                        ? Decision.allow() : Decision.deny("OWNER_ACTION_VERB_REQUIRED");
            case "BACK":
                if (!WORKER_PACKAGE.equals(currentPackage) && !OWNER_PACKAGE.equals(currentPackage))
                    return Decision.deny("FOREGROUND_PACKAGE_DENIED");
                return hasAny(request, "geri", "back", "ارجع") ? Decision.allow() : Decision.deny("OWNER_ACTION_VERB_REQUIRED");
            case "HOME":
                return hasAny(request, "ana ekran", "home") ? Decision.allow() : Decision.deny("OWNER_ACTION_VERB_REQUIRED");
            case "RECENTS":
                return hasAny(request, "son uygulamalar", "recents") ? Decision.allow() : Decision.deny("OWNER_ACTION_VERB_REQUIRED");
            case "NOTIFICATION_ACTION":
                return hasAny(request, "bildirim", "notification") ? Decision.allow() : Decision.deny("OWNER_ACTION_VERB_REQUIRED");
            case "SCREENSHOT":
            case "SHARE":
            case "OPEN_FILE":
            case "PICK_FILE":
                return Decision.deny("TOOL_REQUIRES_EXPLICIT_APP_LEVEL_FLOW");
            default:
                return Decision.deny("TOOL_NOT_ALLOWLISTED");
        }
    }

    public static boolean explicitActionIntent(String request) {
        String n = normalize(request);
        return hasAny(n, "aç", "ac", "tıkla", "tikla", "dokun", "yaz", "gir", "kaydır", "kaydir",
                "geri", "gönder", "gonder", "uygula", "yap", "çalıştır", "calistir",
                "open", "launch", "click", "tap", "type", "enter", "swipe", "scroll",
                "back", "home", "recents", "send", "execute", "sor",
                "افتح", "اضغط", "اكتب", "اسحب", "ارجع", "نفذ", "أرسل", "ارسل");
    }

    static String canonical(String tool) {
        String t = tool == null ? "" : tool.trim().toUpperCase(Locale.ROOT);
        switch (t) {
            case "SCREEN_READ": return "READ_SCREEN";
            case "LAUNCH_WORKER": return "OPEN_APP";
            case "CLICK_TEXT": return "CLICK_ELEMENT";
            default: return t;
        }
    }

    private static boolean mentionsWorker(String request) {
        return hasAny(request, "cihat", "chatbot", "com codespaceapps aichat", "worker");
    }
    private static boolean isSendTarget(String target) {
        String n = normalize(target);
        return hasAny(n, "gönder", "gonder", "send", "send message", "أرسل", "ارسل");
    }
    private static boolean requestContainsTarget(String request, String target) {
        String t = normalize(target).trim();
        return !t.isEmpty() && request.contains(" " + t + " ");
    }
    private static String firstNonEmpty(String a, String b) {
        String x = a == null ? "" : a.trim();
        return x.isEmpty() ? (b == null ? "" : b.trim()) : x;
    }
    private static String normalize(String request) {
        if (request == null) return " ";
        return " " + request.toLowerCase(Locale.ROOT)
                .replaceAll("[^\\p{L}\\p{N}]+", " ")
                .replaceAll("\\s+", " ").trim() + " ";
    }
    private static boolean hasAny(String normalized, String... phrases) {
        for (String phrase : phrases) {
            String p = normalize(phrase).trim();
            if (!p.isEmpty() && normalized.contains(" " + p + " ")) return true;
        }
        return false;
    }
}
