package com.mehmetcerdik.ownerai;

import android.os.RemoteException;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public final class ShizukuShellService extends IShizukuShellService.Stub {
    private static final String BRIDGE_PACKAGE = "com.mehmetcerdik.ownerbridge";
    private static final String BRIDGE_COMPONENT =
            "com.mehmetcerdik.ownerbridge/com.mehmetcerdik.ownerbridge.BridgeAccessibilityService";
    private static final String BRIDGE_SHA256 =
            "b3d950746e92bf09fdb9730cbe1a7d770e7363a104852182cc3b1d80542b33b4";
    private static final String TEMP_APK =
            "/data/local/tmp/MEHMET_OWNER_BRIDGE_1.2.1_VC4_GEN2_SIGNED.apk";
    private static final int MAX_BRIDGE_BYTES = 2 * 1024 * 1024;

    public ShizukuShellService() {}

    @Override
    public String bootstrapBridge(byte[] apkBytes) throws RemoteException {
        StringBuilder evidence = new StringBuilder();
        try {
            if (apkBytes == null || apkBytes.length == 0 || apkBytes.length > MAX_BRIDGE_BYTES) {
                return "STATUS=EMBEDDED_BRIDGE_INVALID_SIZE\n";
            }
            String actual = sha256(apkBytes);
            evidence.append("EMBEDDED_BRIDGE_SHA256=").append(actual).append('\n');
            if (!BRIDGE_SHA256.equals(actual)) {
                evidence.append("STATUS=EMBEDDED_BRIDGE_HASH_MISMATCH\n");
                return evidence.toString();
            }

            File tmp = new File(TEMP_APK);
            try (FileOutputStream out = new FileOutputStream(tmp, false)) {
                out.write(apkBytes);
                out.flush();
            }

            evidence.append(run("/system/bin/chmod", "0644", TEMP_APK));
            ExecResult install = exec("/system/bin/pm", "install", "-r", "--user", "0", TEMP_APK);
            evidence.append("INSTALL_EXIT=").append(install.exitCode).append('\n');
            evidence.append("INSTALL_OUTPUT=").append(safe(install.output)).append('\n');
            try { tmp.delete(); } catch (Throwable ignored) {}

            if (install.exitCode != 0 || install.output == null || !install.output.contains("Success")) {
                if (install.output != null && install.output.contains("INSTALL_FAILED_UPDATE_INCOMPATIBLE")) {
                    evidence.append("STATUS=BRIDGE_INSTALL_FAILED_SIGNATURE_CONFLICT\n");
                } else {
                    evidence.append("STATUS=BRIDGE_INSTALL_FAILED\n");
                }
                return evidence.toString();
            }

            evidence.append(unlockInternal());
            return evidence.toString();
        } catch (Throwable t) {
            try { new File(TEMP_APK).delete(); } catch (Throwable ignored) {}
            evidence.append("STATUS=SHIZUKU_BOOTSTRAP_FAILED\n");
            evidence.append("ERROR=").append(t.getClass().getSimpleName())
                    .append(":").append(t.getMessage() == null ? "" : t.getMessage()).append('\n');
            return evidence.toString();
        }
    }

    @Override
    public String unlockBridgeAccessibility() throws RemoteException {
        try {
            return unlockInternal();
        } catch (Throwable t) {
            return "STATUS=SHIZUKU_UNLOCK_FAILED\nERROR="
                    + t.getClass().getSimpleName() + ":"
                    + (t.getMessage() == null ? "" : t.getMessage()) + "\n";
        }
    }

    private String unlockInternal() throws Exception {
        StringBuilder evidence = new StringBuilder();
        evidence.append(run("/system/bin/appops", "set",
                BRIDGE_PACKAGE, "ACCESS_RESTRICTED_SETTINGS", "allow"));

        String current = runValue("/system/bin/settings", "get",
                "secure", "enabled_accessibility_services");
        Set<String> enabled = new LinkedHashSet<>();
        if (current != null && !current.isBlank() && !"null".equalsIgnoreCase(current.trim())) {
            for (String part : current.trim().split(":")) {
                if (!part.isBlank()) enabled.add(part.trim());
            }
        }
        enabled.add(BRIDGE_COMPONENT);
        String joined = String.join(":", enabled);

        evidence.append(run("/system/bin/settings", "put",
                "secure", "enabled_accessibility_services", joined));
        evidence.append(run("/system/bin/settings", "put",
                "secure", "accessibility_enabled", "1"));

        String appOps = runValue("/system/bin/appops", "get",
                BRIDGE_PACKAGE, "ACCESS_RESTRICTED_SETTINGS");
        String services = runValue("/system/bin/settings", "get",
                "secure", "enabled_accessibility_services");
        String enabledFlag = runValue("/system/bin/settings", "get",
                "secure", "accessibility_enabled");
        String packagePath = runValue("/system/bin/pm", "path", BRIDGE_PACKAGE);

        boolean componentPresent = services != null && services.contains(BRIDGE_COMPONENT);
        boolean accessibilityEnabled = "1".equals(enabledFlag == null ? "" : enabledFlag.trim());
        boolean packagePresent = packagePath != null && packagePath.contains("package:");

        evidence.append("READBACK_PACKAGE_PATH=").append(safe(packagePath)).append('\n');
        evidence.append("READBACK_APP_OP=").append(safe(appOps)).append('\n');
        evidence.append("READBACK_ENABLED_SERVICES=").append(safe(services)).append('\n');
        evidence.append("READBACK_ACCESSIBILITY_ENABLED=").append(safe(enabledFlag)).append('\n');
        evidence.append("PACKAGE_PRESENT=").append(packagePresent).append('\n');
        evidence.append("COMPONENT_PRESENT=").append(componentPresent).append('\n');
        evidence.append("ACCESSIBILITY_ENABLED=").append(accessibilityEnabled).append('\n');
        evidence.append("STATUS=")
                .append(packagePresent && componentPresent && accessibilityEnabled
                        ? "ONE_TAP_BOOTSTRAP_OK" : "ONE_TAP_BOOTSTRAP_READBACK_FAILED")
                .append('\n');
        return evidence.toString();
    }

    private static String run(String... command) throws Exception {
        ExecResult r = exec(command);
        return "CMD=" + String.join(" ", command)
                + "\nEXIT=" + r.exitCode
                + "\nOUTPUT=" + safe(r.output) + "\n";
    }

    private static String runValue(String... command) throws Exception {
        ExecResult r = exec(command);
        if (r.exitCode != 0) {
            throw new IllegalStateException("command failed (" + r.exitCode + "): "
                    + String.join(" ", command) + " :: " + r.output);
        }
        return r.output == null ? "" : r.output.trim();
    }

    private static ExecResult exec(String... command) throws Exception {
        Process p = new ProcessBuilder(command).redirectErrorStream(true).start();
        List<String> lines = new ArrayList<>();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(p.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) lines.add(line);
        }
        int rc = p.waitFor();
        return new ExecResult(rc, String.join("\n", lines));
    }

    private static String sha256(byte[] bytes) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
        StringBuilder out = new StringBuilder();
        for (byte b : digest) out.append(String.format(Locale.ROOT, "%02x", b & 0xff));
        return out.toString();
    }

    private static String safe(String value) {
        return value == null ? "" : value.replace('\n', ' ').replace('\r', ' ').trim();
    }

    @Override
    public void destroy() {
        System.exit(0);
    }

    private static final class ExecResult {
        final int exitCode;
        final String output;

        ExecResult(int exitCode, String output) {
            this.exitCode = exitCode;
            this.output = output;
        }
    }
}
