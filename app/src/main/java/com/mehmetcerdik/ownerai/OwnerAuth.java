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
        if (OwnerSession.isAuthorized()) {
            onSuccess.run();
            return;
        }
        if (isDebugEmulator()) {
            OwnerSession.authorize();
            onSuccess.run();
            return;
        }

        int authenticators = Build.VERSION.SDK_INT >= 30
                ? BiometricManager.Authenticators.BIOMETRIC_STRONG | BiometricManager.Authenticators.DEVICE_CREDENTIAL
                : BiometricManager.Authenticators.BIOMETRIC_WEAK | BiometricManager.Authenticators.DEVICE_CREDENTIAL;

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
                        OwnerSession.authorize();
                        onSuccess.run();
                    }

                    @Override public void onAuthenticationError(int errorCode, CharSequence errString) {
                        onFailure.accept("OWNER_AUTH_ERROR:" + errorCode);
                    }

                    @Override public void onAuthenticationFailed() {
                        onFailure.accept("OWNER_AUTH_FAILED");
                    }
                });

        BiometricPrompt.PromptInfo info = new BiometricPrompt.PromptInfo.Builder()
                .setTitle("MEHMET Owner doğrulaması")
                .setSubtitle("Devam etmek için biyometri veya cihaz kilidi ile doğrula")
                .setAllowedAuthenticators(authenticators)
                .setConfirmationRequired(true)
                .build();
        prompt.authenticate(info);
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
