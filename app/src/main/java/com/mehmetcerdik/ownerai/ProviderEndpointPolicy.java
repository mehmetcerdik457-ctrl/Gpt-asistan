package com.mehmetcerdik.ownerai;

import java.net.URI;
import java.util.Locale;

public final class ProviderEndpointPolicy {
    public static final String CANONICAL = "https://api.openai.com/v1/responses";

    private ProviderEndpointPolicy() {}

    public static String canonicalForStorage(String candidate) {
        String value = candidate == null || candidate.trim().isEmpty() ? CANONICAL : candidate.trim();
        if (!isAllowed(value)) throw new IllegalArgumentException("PROVIDER_ENDPOINT_DENIED");
        return CANONICAL;
    }

    public static boolean isAllowed(String candidate) {
        try {
            URI uri = URI.create(candidate == null ? "" : candidate.trim());
            if (!"https".equalsIgnoreCase(uri.getScheme())) return false;
            String host = uri.getHost();
            if (host == null || !"api.openai.com".equals(host.toLowerCase(Locale.ROOT))) return false;
            if (uri.getPort() != -1 && uri.getPort() != 443) return false;
            if (!"/v1/responses".equals(uri.getRawPath())) return false;
            if (uri.getRawUserInfo() != null) return false;
            if (uri.getRawQuery() != null) return false;
            if (uri.getRawFragment() != null) return false;
            if (uri.getAuthority() == null) return false;
            String authority = uri.getAuthority().toLowerCase(Locale.ROOT);
            return "api.openai.com".equals(authority) || "api.openai.com:443".equals(authority);
        } catch (RuntimeException e) {
            return false;
        }
    }

    public static void requireAllowed(String candidate) {
        if (!isAllowed(candidate)) throw new SecurityException("PROVIDER_ENDPOINT_DENIED");
    }
}
