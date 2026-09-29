package com.mehmetcerdik.ownerai;

import android.os.Build;

import androidx.biometric.BiometricManager;
import androidx.biometric.BiometricPrompt;
import androidx.core.content.ContextCompat;
import androidx.fragment.app.FragmentActivity;

import com.example.gptasistan.BuildConfig;

import java.util.Locale;
import java.util.function.Consumer;

public final class OwnerAuth {
    private OwnerAuth() {}

    public static void require(FragmentActivity activity, Runnable onSuccess, Consumer<String> onFailure) {
        if (OwnerSession.isAuthorized(activity)) {
            onSuccess.run();
            return;
        }
        prompt(activity, onSuccess, onFailure);
    }

    public static void requireFresh(FragmentActivity activity, Runnable onSuccess, Consumer<String> onFailure) {
        prompt(activity, onSuccess, onFailure);
    }

    private static void prompt(FragmentActivity activity, Runnable onSuccess, Consumer<String> onFailure) {
        if (isDebugEmulator()) {
            OwnerSession.authorizeDebug();
            onSuccess.run();
            return;
        }

        // API 30+ supports the secure STRONG-or-device-credential combination.
        // Older releases use BIOMETRIC_STRONG only; never downgrade release auth to WEAK.
        int authenticators = Build.VERSION.SDK_INT >= 30
                ? BiometricManager.Authenticators.BIOMETRIC_STRONG | BiometricManager.Authenticators.DEVICE_CREDENTIAL
                : BiometricManager.Authenticators.BIOMETRIC_STRONG;

        int availability = BiometricManager.from(activity).canAuthenticate(authenticators);
        if (availability != BiometricManager.BIOMETRIC_SUCCESS) {
            onFailure.accept("OWNER_AUTH_UNAVAILABLE:" + availability);
            return;
        }

        BiometricPrompt prompt = new BiometricPrompt(
                activity,
                ContextCompat.getMainExecutor(activity),
                new BiometricPrompt.AuthenticationCallback() {
                    @Override public void onAuthenticationSucceeded(BiometricPrompt.AuthenticationResult result) {
                        try {
                            OwnerSession.authorize(activity);
                            onSuccess.run();
                        } catch (Throwable t) {
                            OwnerSession.clear();
                            onFailure.accept("TRUSTED_DEVICE_SESSION_FAILED");
                        }
                    }

                    @Override public void onAuthenticationError(int errorCode, CharSequence errString) {
                        OwnerSession.clear();
                        onFailure.accept("OWNER_AUTH_ERROR:" + errorCode);
                    }

                    @Override public void onAuthenticationFailed() {
                        onFailure.accept("OWNER_AUTH_FAILED");
                    }
                });

        BiometricPrompt.PromptInfo.Builder infoBuilder = new BiometricPrompt.PromptInfo.Builder()
                .setTitle("MEHMET Owner doğrulaması")
                .setSubtitle("Owner kimliği + kayıtlı cihaz kanıtı için doğrula")
                .setAllowedAuthenticators(authenticators)
                .setConfirmationRequired(true);
        if (Build.VERSION.SDK_INT < 30) {
            // Required when DEVICE_CREDENTIAL is not one of the allowed authenticators.
            infoBuilder.setNegativeButtonText("İptal");
        }
        prompt.authenticate(infoBuilder.build());
    }

    private static boolean isDebugEmulator() {
        if (!BuildConfig.DEBUG) return false;
        String fingerprint = Build.FINGERPRINT == null ? "" : Build.FINGERPRINT.toLowerCase(Locale.ROOT);
        String model = Build.MODEL == null ? "" : Build.MODEL.toLowerCase(Locale.ROOT);
        String hardware = Build.HARDWARE == null ? "" : Build.HARDWARE.toLowerCase(Locale.ROOT);
        return fingerprint.startsWith("generic")
                || fingerprint.contains("emulator")
                || model.contains("sdk_gphone")
                || model.contains("emulator")
                || hardware.contains("ranchu")
                || hardware.contains("goldfish");
    }
}
