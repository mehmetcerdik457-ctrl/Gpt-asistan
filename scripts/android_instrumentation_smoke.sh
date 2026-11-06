#!/usr/bin/env bash
# Run prebuilt, SHA-bound Android instrumentation without Gradle inside emulator.
# Tests may clear only synthetic debug-emulator databases (InstrumentationSafety).
set -euo pipefail
apk_dir=build/emulator/apk
evidence_dir=build/emulator/evidence
mkdir -p "$evidence_dir"

(cd "$apk_dir" && sha256sum -c APK-SHA256SUMS && sha256sum -c TEST-APK-SHA256SUMS) |
  tee "$evidence_dir/instrumentation-hashes.txt"

python3 - <<'PY'
import json, os
from pathlib import Path
p = Path("build/emulator/apk")
m = json.loads((p / "apk-metadata.json").read_text())
assert m["source_commit"] == os.environ["KRAL_EXPECTED_SOURCE_SHA"], "SOURCE_SHA_MISMATCH"
assert m["package"] == "com.example.gptasistan.genesis", "PACKAGE_MISMATCH"
assert m["signature_verified"] is True and m["debuggable"] is True, "DEBUG_APK_SIGNATURE_INVALID"
PY

timeout 20 adb -e get-state | tee "$evidence_dir/adb-state.txt"
test "$(tr -d '\r\n' < "$evidence_dir/adb-state.txt")" = device
test "$(timeout 20 adb -e shell getprop ro.kernel.qemu | tr -d '\r\n')" = 1
test "$(timeout 20 adb -e shell getprop sys.boot_completed | tr -d '\r\n')" = 1
api_level="$(timeout 20 adb -e shell getprop ro.build.version.sdk | tr -d '\r\n')"
test "$api_level" = "$KRAL_EMULATOR_API" || { echo "EMULATOR_API_MISMATCH"; exit 1; }
printf '%s\n' "$api_level" > "$evidence_dir/instrumentation-api-level.txt"

timeout 90 adb -e install -t "$apk_dir/app-debug.apk" 2>&1 |
  tee "$evidence_dir/instrumentation-install-app.txt"
timeout 90 adb -e install -t "$apk_dir/app-debug-androidTest.apk" 2>&1 |
  tee "$evidence_dir/instrumentation-install-test.txt"

# Android 13+ requires an explicit notification grant. Apply the synthetic CI
# fixture's grant before instrumentation: changing it during a test can kill the
# application process and invalidate the real JobScheduler service observation.
if (( api_level >= 33 )); then
  timeout 20 adb -e shell pm grant com.example.gptasistan.genesis android.permission.POST_NOTIFICATIONS 2>&1 |
    tee "$evidence_dir/instrumentation-notification-permission.txt"
fi

# Fail on nonzero adb status AND malformed/missing test-runner success summary.
# The two-phase installation-copy fixture runs only in its own fresh emulator job.
timeout 240 adb -e shell am instrument -w -r \
  -e notClass com.example.gptasistan.BackupInstallationTest \
  com.example.gptasistan.genesis.test/androidx.test.runner.AndroidJUnitRunner 2>&1 |
  tee "$evidence_dir/instrumentation-result.txt"

python3 scripts/android_instrumentation_evidence.py \
  "$evidence_dir/instrumentation-result.txt" "$apk_dir" \
  "$evidence_dir/instrumentation-summary.json"
