#!/usr/bin/env bash
# Install and inspect the CI-built candidate on a fresh emulator only.
set -euo pipefail

apk_dir=build/emulator/apk
evidence_dir=build/emulator/evidence
package=com.example.gptasistan.genesis.cihatpreview
mkdir -p "$evidence_dir"

capture_evidence() {
  result=$?
  trap - EXIT
  timeout 10 adb -e logcat -d -v threadtime > "$evidence_dir/logcat.txt" 2>&1 || true
  timeout 10 adb -e shell dumpsys activity activities > "$evidence_dir/activities.txt" 2>&1 || true
  printf '%s\n' "$result" > "$evidence_dir/exit-code.txt"
  exit "$result"
}
trap capture_evidence EXIT

(cd "$apk_dir" && sha256sum -c APK-SHA256SUMS) | tee "$evidence_dir/apk-hash-check.txt"
cp "$apk_dir/apk-metadata.json" "$evidence_dir/apk-metadata.json"
adb devices -l > "$evidence_dir/devices.txt"
adb -e shell getprop ro.product.cpu.abi > "$evidence_dir/abi.txt"
adb -e shell getprop ro.build.version.sdk > "$evidence_dir/api-level.txt"
adb -e shell getprop ro.kernel.qemu > "$evidence_dir/is-emulator.txt"
python3 - <<'PY'
import json
import os
from pathlib import Path

root = Path('build/emulator/evidence')
metadata = json.loads((root / 'apk-metadata.json').read_text())
assert metadata['package'] == 'com.example.gptasistan.genesis.cihatpreview', 'Unexpected APK package'
assert metadata['source_commit'] == os.environ['KRAL_EXACT_HEAD_SHA'], 'APK/source commit mismatch'
assert (root / 'is-emulator.txt').read_text().strip() == '1', 'Target must be an emulator'
assert (root / 'api-level.txt').read_text().strip() == '30', 'Unexpected emulator API'
assert (root / 'abi.txt').read_text().strip() == 'x86_64', 'Unexpected emulator architecture'
PY

timeout 15 adb -e uninstall "$package" >/dev/null 2>&1 || true
timeout 60 adb -e install -t "$apk_dir/app-debug.apk" 2>&1 | tee "$evidence_dir/install.txt"
timeout 30 adb -e shell am start -W -n "$package/com.example.gptasistan.MainActivity" | tee "$evidence_dir/launch.txt"

# Wait for rendering without granting access or dismissing the app's owner lock.
for attempt in $(seq 1 10); do
  if timeout 15 adb -e shell uiautomator dump /sdcard/genesis-window.xml > "$evidence_dir/ui-dump.txt" 2>&1; then
    adb -e pull /sdcard/genesis-window.xml "$evidence_dir/window.xml" > "$evidence_dir/ui-pull.txt" 2>&1
    if python3 - <<'PY'
from pathlib import Path
import xml.etree.ElementTree as ET

nodes = ET.parse(Path('build/emulator/evidence/window.xml')).getroot().iter('node')
texts = {node.get('text', '') for node in nodes}
assert 'KRAL ASİSTAN — cihaz kilidiyle aç' in texts, 'Owner lock title missing'
assert 'Kilidi aç' in texts, 'Owner unlock button missing'
PY
    then
      break
    fi
  fi
  if [ "$attempt" = 10 ]; then
    echo 'Owner lock screen did not appear' >&2
    exit 1
  fi
  sleep 1
done
adb -e shell pidof "$package" | tee "$evidence_dir/pid.txt"
test -s "$evidence_dir/pid.txt"
python3 - <<'PY'
import json
import os
from pathlib import Path

root = Path('build/emulator/evidence')
apk = json.loads((root / 'apk-metadata.json').read_text())
result = {
    'source_commit': os.environ['KRAL_EXACT_HEAD_SHA'],
    'github_run_id': os.environ['GITHUB_RUN_ID'],
    'apk_sha256': apk['sha256'],
    'package': apk['package'],
    'api_level': 30,
    'abi': 'x86_64',
    'installation_passed': True,
    'launch_passed': True,
    'owner_lock_screen_visible': True,
    'owner_authentication_attempted': False,
    'persistence_on_emulator_tested': False,
    'physical_phone_tested': False,
    'live_model_tested': False,
}
(root / 'emulator-result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
PY
