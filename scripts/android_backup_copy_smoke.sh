#!/usr/bin/env bash
# Fresh debug-emulator fixture only. Never overwrite/uninstall a pre-existing app.
set -euo pipefail

apk_dir=build/emulator/apk
evidence_dir=build/backup-copy/evidence
backup_package=com.example.gptasistan.genesis
backup_test_package=com.example.gptasistan.genesis.test
backup_class=com.example.gptasistan.BackupInstallationTest
backup_archive=kral-installation-backup.bin
backup_owned_app=0
backup_owned_test=0
mkdir -p "$evidence_dir"
python3 - <<'PY'
from pathlib import Path
result = Path('build/backup-copy/evidence/backup-copy-result.json')
if result.is_symlink() or result.is_dir():
    raise ValueError('BACKUP_COPY_RESULT_PATH_INVALID')
result.unlink(missing_ok=True)  # A failed repeated invocation cannot retain a stale success record.
PY

finish_backup_evidence() {
  backup_exit=$?
  trap - EXIT
  printf '%s\n' "$backup_exit" > "$evidence_dir/exit-code.txt"
  exit "$backup_exit"
}
trap finish_backup_evidence EXIT

# Check the real APK manifests/signatures before any installation or fixture write.
backup_tools="${ANDROID_HOME:?ANDROID_HOME required}/build-tools/36.0.0"
"$backup_tools/aapt" dump badging "$apk_dir/app-debug.apk" > "$evidence_dir/app-badging.txt"
"$backup_tools/aapt" dump badging "$apk_dir/app-debug-androidTest.apk" > "$evidence_dir/test-badging.txt"
"$backup_tools/apksigner" verify --verbose --print-certs "$apk_dir/app-debug.apk" > "$evidence_dir/app-signature.txt"
"$backup_tools/apksigner" verify --verbose --print-certs "$apk_dir/app-debug-androidTest.apk" > "$evidence_dir/test-signature.txt"
python3 scripts/android_backup_copy_evidence.py "$evidence_dir" "$apk_dir" --preflight

backup_serial="$(timeout 20 adb -e get-serialno | tr -d '\r\n')"
[[ "$backup_serial" =~ ^emulator-[0-9]+$ ]] || { echo 'DISPOSABLE_EMULATOR_SERIAL_REQUIRED' >&2; exit 1; }
printf '%s\n' "$backup_serial" > "$evidence_dir/device-serial.txt"

backup_device_guard() {
  test "$(timeout 20 adb -s "$backup_serial" get-state | tr -d '\r\n')" = device
  test "$(timeout 20 adb -s "$backup_serial" shell getprop ro.kernel.qemu | tr -d '\r\n')" = 1
  test "$(timeout 20 adb -s "$backup_serial" shell getprop sys.boot_completed | tr -d '\r\n')" = 1
  test "${KRAL_EMULATOR_API:?}" = 30
  test "$(timeout 20 adb -s "$backup_serial" shell getprop ro.build.version.sdk | tr -d '\r\n')" = 30
  test "$(timeout 20 adb -s "$backup_serial" shell getprop ro.product.cpu.abi | tr -d '\r\n')" = x86_64
}

backup_require_absent() {
  local backup_name="$1" backup_output="$2" backup_path_status
  set +e
  timeout 20 adb -s "$backup_serial" shell pm path "$backup_name" > "$backup_output" 2>&1
  backup_path_status=$?
  set -e
  # pm may return 0 or 1 for an absent package; transport failures/timeouts fail closed.
  test "$backup_path_status" -eq 0 || test "$backup_path_status" -eq 1
  test ! -s "$backup_output" || { echo 'PREEXISTING_PACKAGE_OR_TRANSPORT_ERROR_REFUSED' >&2; exit 1; }
}

backup_device_guard
timeout 20 adb -s "$backup_serial" shell getprop ro.kernel.qemu > "$evidence_dir/qemu.txt"
timeout 20 adb -s "$backup_serial" shell getprop ro.build.version.sdk > "$evidence_dir/api-level.txt"
timeout 20 adb -s "$backup_serial" shell getprop ro.product.cpu.abi > "$evidence_dir/abi.txt"
backup_require_absent "$backup_package" "$evidence_dir/app-before.txt"
backup_require_absent "$backup_test_package" "$evidence_dir/test-before.txt"

timeout 90 adb -s "$backup_serial" install -t "$apk_dir/app-debug.apk" 2>&1 | tee "$evidence_dir/source-install-app.txt"
backup_owned_app=1
timeout 90 adb -s "$backup_serial" install -t "$apk_dir/app-debug-androidTest.apk" 2>&1 | tee "$evidence_dir/source-install-test.txt"
backup_owned_test=1
timeout 300 adb -s "$backup_serial" shell am instrument -w -r \
  -e class "$backup_class" -e backup_phase export \
  "$backup_test_package/androidx.test.runner.AndroidJUnitRunner" 2>&1 | tee "$evidence_dir/export-result.txt"
timeout 30 adb -s "$backup_serial" exec-out run-as "$backup_package" cat "files/$backup_archive" > "$evidence_dir/$backup_archive"
python3 scripts/android_backup_copy_evidence.py "$evidence_dir" "$apk_dir" --export-only
backup_hash="$(sha256sum "$evidence_dir/$backup_archive" | cut -d ' ' -f 1)"
printf '%s  %s\n' "$backup_hash" "$backup_archive" > "$evidence_dir/BACKUP-SHA256SUMS"

# Only these two packages were proven absent and installed by this script.
# No -r, pm clear, database/key extraction, permission changes or physical device.
backup_device_guard
test "$backup_owned_app" -eq 1 && test "$backup_owned_test" -eq 1
timeout 60 adb -s "$backup_serial" uninstall "$backup_test_package" 2>&1 | tee "$evidence_dir/source-uninstall-test.txt"
backup_owned_test=0
timeout 60 adb -s "$backup_serial" uninstall "$backup_package" 2>&1 | tee "$evidence_dir/source-uninstall-app.txt"
backup_owned_app=0
backup_require_absent "$backup_package" "$evidence_dir/app-between.txt"
backup_require_absent "$backup_test_package" "$evidence_dir/test-between.txt"
timeout 90 adb -s "$backup_serial" install -t "$apk_dir/app-debug.apk" 2>&1 | tee "$evidence_dir/target-install-app.txt"
backup_owned_app=1
timeout 90 adb -s "$backup_serial" install -t "$apk_dir/app-debug-androidTest.apk" 2>&1 | tee "$evidence_dir/target-install-test.txt"
backup_owned_test=1
backup_device_guard
timeout 20 adb -s "$backup_serial" shell -T run-as "$backup_package" mkdir -p files
# Non-PTY stdin keeps binary bytes intact; dd needs no remote-shell redirection quoting.
timeout 30 adb -s "$backup_serial" shell -T run-as "$backup_package" dd "of=files/$backup_archive" \
  < "$evidence_dir/$backup_archive" > "$evidence_dir/import-archive.txt" 2>&1
timeout 20 adb -s "$backup_serial" shell -T run-as "$backup_package" chmod 600 "files/$backup_archive"
timeout 300 adb -s "$backup_serial" shell am instrument -w -r \
  -e class "$backup_class" -e backup_phase restore -e backup_sha256 "$backup_hash" \
  "$backup_test_package/androidx.test.runner.AndroidJUnitRunner" 2>&1 | tee "$evidence_dir/restore-result.txt"
python3 scripts/android_backup_copy_evidence.py "$evidence_dir" "$apk_dir"
