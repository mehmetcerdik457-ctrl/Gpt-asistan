package com.mehmetcerdik.ownerbridge;

import java.util.Locale;

final class SecretClassifier {
    private static final String[] TOKENS = {
            "password", "parola", "şifre", "sifre", "pin", "otp", "one time", "one-time",
            "verification code", "doğrulama kod", "dogrulama kod", "cvv", "cvc", "card security",
            "api key", "apikey", "access token", "refresh token", "bearer", "secret", "client_secret",
            "recovery code", "kurtarma kod", "seed phrase", "recovery phrase", "mnemonic", "private key"
    };

    private SecretClassifier() {}

    static boolean isSensitiveMetadata(String text, String desc, String hint, String viewId) {
        String all = (nz(text) + " " + nz(desc) + " " + nz(hint) + " " + nz(viewId)).toLowerCase(Locale.ROOT);
        for (String token : TOKENS) if (all.contains(token)) return true;
        return false;
    }

    private static String nz(String s) { return s == null ? "" : s; }
}
