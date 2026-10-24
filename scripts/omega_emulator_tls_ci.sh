#!/usr/bin/env bash
set -euo pipefail
mkdir -p build/omega-emulator-tls app/src/androidTest/assets
tmpdir="$(mktemp -d)"
chmod 700 "$tmpdir"
server_pid=""
cleanup() {
  if [ -n "$server_pid" ]; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  adb -e reverse --remove tcp:18443 >/dev/null 2>&1 || true
  rm -rf "$tmpdir"
}
trap cleanup EXIT
openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -subj '/CN=OMEGA-CI-TLS-ONLY' \
  -addext 'subjectAltName=IP:127.0.0.1' \
  -keyout "$tmpdir/key.pem" -out "$tmpdir/cert.pem" >/dev/null 2>&1
openssl x509 -in "$tmpdir/cert.pem" -outform DER \
  -out app/src/androidTest/assets/omega-ci-loopback-cert.der
chmod 600 "$tmpdir/key.pem"
python3 scripts/omega_ci_tls_loopback.py --omega-dir omega-pinned \
  --cert "$tmpdir/cert.pem" --key "$tmpdir/key.pem" \
  > build/omega-emulator-tls/server.log 2>&1 &
server_pid=$!
for i in $(seq 1 30); do
  if curl --silent --show-error --fail --cacert "$tmpdir/cert.pem" \
    https://127.0.0.1:18443/api/health \
    -o build/omega-emulator-tls/health.json 2>/dev/null; then break; fi
  if ! kill -0 "$server_pid" 2>/dev/null; then exit 2; fi
  sleep 1
done
test -s build/omega-emulator-tls/health.json
python3 - <<'PY'
import json
from pathlib import Path
x=json.loads(Path("build/omega-emulator-tls/health.json").read_text())
assert x["status"]=="PASS" and x["owner_identity_verified"] is False
assert x["execution_enabled"] is False
print("OMEGA_TLS_SAFE_HEALTH=PASS")
PY
code="$(curl --silent --show-error --cacert "$tmpdir/cert.pem" \
  -o build/omega-emulator-tls/models.json -w '%{http_code}' \
  https://127.0.0.1:18443/api/models)"
test "$code" = "403"
code="$(curl --silent --show-error --cacert "$tmpdir/cert.pem" \
  -H 'Content-Type: application/json' \
  -d '{"message":"synthetic"}' \
  -o build/omega-emulator-tls/chat.json -w '%{http_code}' \
  https://127.0.0.1:18443/api/chat)"
test "$code" = "403"
python3 - <<'PY'
import json
from pathlib import Path
for name in ("models","chat"):
    x=json.loads(Path(f"build/omega-emulator-tls/{name}.json").read_text())
    assert x["error"]=="OWNER_EXECUTION_NOT_APPROVED"
print("OMEGA_PROVIDER_DENIAL=PASS")
PY
adb -e reverse tcp:18443 tcp:18443
adb -e reverse --list | grep -F 'tcp:18443 tcp:18443'
./gradlew :app:connectedDebugAndroidTest \
  -Pandroid.testInstrumentationRunnerArguments.class=com.example.gptasistan.OmegaHttpsEmulatorTest,com.example.gptasistan.OmegaSignedWireEmulatorTest \
  -Pandroid.testInstrumentationRunnerArguments.omega_tls_test=true \
  --no-daemon
python3 - <<'PY'
from pathlib import Path
import xml.etree.ElementTree as ET
paths=list(Path("app/build/outputs/androidTest-results/connected").rglob("TEST-*.xml"))
assert paths, "Android instrumentation JUnit XML missing"
cases=[]
fail=0
skip=0
for path in paths:
    root=ET.parse(path).getroot()
    for test in root.iter("testcase"):
        name=test.attrib.get("classname","")
        if name in (
            "com.example.gptasistan.OmegaHttpsEmulatorTest",
            "com.example.gptasistan.OmegaSignedWireEmulatorTest",
        ):
            cases.append((name, test.attrib.get("name","")))
            fail += sum(child.tag in ("failure","error") for child in test)
            skip += sum(child.tag == "skipped" for child in test)
names=set(cases)
required={
    ("com.example.gptasistan.OmegaHttpsEmulatorTest",
     "emulatorToOmegaRealTlsIsReadOnly"),
    ("com.example.gptasistan.OmegaHttpsEmulatorTest",
     "releaseDefaultTrustMustRejectEphemeralCertificate"),
    ("com.example.gptasistan.OmegaSignedWireEmulatorTest",
     "androidGeneratedP256DualProofIsValidButNeverAuthorizes"),
}
assert names==required, ("unexpected missing/extra tests",names)
assert len(cases)==3 and fail==0 and skip==0,(cases,fail,skip)
print("OMEGA_ANDROID_REAL_TLS_AND_SIGNED_P256=PASS")
print("OMEGA_OWNER_DEVICE_ACCEPTANCE=NOT_TESTED")
PY
