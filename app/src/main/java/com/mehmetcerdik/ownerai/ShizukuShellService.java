package com.mehmetcerdik.ownerai;

import android.os.RemoteException;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public final class ShizukuShellService extends IShizukuShellService.Stub {
    private static final String BRIDGE_PACKAGE = "com.mehmetcerdik.ownerbridge";
    private static final String BRIDGE_COMPONENT =
            "com.mehmetcerdik.ownerbridge/com.mehmetcerdik.ownerbridge.BridgeAccessibilityService";

    public ShizukuShellService() {}

    @Override
    public String unlockBridgeAccessibility() throws RemoteException {
        StringBuilder evidence = new StringBuilder();
        try {
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

            boolean componentPresent = services != null && services.contains(BRIDGE_COMPONENT);
            boolean accessibilityEnabled = "1".equals(enabledFlag == null ? "" : enabledFlag.trim());

            evidence.append("READBACK_APP_OP=").append(safe(appOps)).append('\n');
            evidence.append("READBACK_ENABLED_SERVICES=").append(safe(services)).append('\n');
            evidence.append("READBACK_ACCESSIBILITY_ENABLED=").append(safe(enabledFlag)).append('\n');
            evidence.append("COMPONENT_PRESENT=").append(componentPresent).append('\n');
            evidence.append("ACCESSIBILITY_ENABLED=").append(accessibilityEnabled).append('\n');

            if (componentPresent && accessibilityEnabled) {
                evidence.append("STATUS=SHIZUKU_BRIDGE_ACCESSIBILITY_ENABLED\n");
            } else {
                evidence.append("STATUS=SHIZUKU_READBACK_FAILED\n");
            }
        } catch (Throwable t) {
            evidence.append("STATUS=SHIZUKU_UNLOCK_FAILED\n");
            evidence.append("ERROR=").append(t.getClass().getSimpleName())
                    .append(":").append(t.getMessage() == null ? "" : t.getMessage()).append('\n');
        }
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
