#!/usr/bin/env bash
set -euo pipefail

PACKAGE="com.example.gptasistan"
SERVICE="${PACKAGE}/${PACKAGE}.PhoneAgentAccessibilityService"
APK="${APK_PATH:-app/build/outputs/apk/debug/app-debug.apk}"
EVIDENCE_DIR="${EVIDENCE_DIR:-emulator-evidence}"
mkdir -p "${EVIDENCE_DIR}"

test -f "${APK}"
APK_SHA256="$(sha256sum "${APK}" | awk '{print $1}')"
printf "%s  %s\n" "${APK_SHA256}" "$(basename "${APK}")" > "${EVIDENCE_DIR}/APK_SHA256"

adb wait-for-device
adb install -r "${APK}" | tee "${EVIDENCE_DIR}/adb-install.txt"

adb shell settings put secure enabled_accessibility_services "${SERVICE}"
adb shell settings put secure accessibility_enabled 1
adb shell am force-stop "${PACKAGE}"
adb shell am start -W -n "${PACKAGE}/.MainActivity" | tee "${EVIDENCE_DIR}/am-start.txt"
sleep 3

ENABLED="$(adb shell settings get secure enabled_accessibility_services | tr -d "\r")"
printf "%s\n" "${ENABLED}" > "${EVIDENCE_DIR}/enabled_accessibility_services.txt"
case ":${ENABLED}:" in
  *":${SERVICE}:"*) ;;
  *) echo "Expected accessibility service is not enabled: ${ENABLED}" >&2; exit 20 ;;
esac

adb shell dumpsys accessibility > "${EVIDENCE_DIR}/dumpsys-accessibility.txt"
adb shell dumpsys package "${PACKAGE}" > "${EVIDENCE_DIR}/dumpsys-package.txt"
grep -q "PhoneAgentAccessibilityService" "${EVIDENCE_DIR}/dumpsys-accessibility.txt"

find_and_tap() {
  local text="$1"
  local attempt xml coords x y
  for attempt in 1 2 3 4 5 6; do
    adb shell uiautomator dump /sdcard/window.xml >/dev/null 2>&1 || true
    xml="${EVIDENCE_DIR}/window-${attempt}.xml"
    adb pull /sdcard/window.xml "${xml}" >/dev/null
    coords="$(python3 - "${xml}" "${text}" <<'PY'
import re, sys, xml.etree.ElementTree as ET
path, needle = sys.argv[1], sys.argv[2]
root = ET.parse(path).getroot()
for node in root.iter("node"):
    label = (node.attrib.get("text") or "") + " " + (node.attrib.get("content-desc") or "")
    if needle in label:
        m = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.attrib.get("bounds",""))
        if not m:
            continue
        x1,y1,x2,y2 = map(int,m.groups())
        print(f"{(x1+x2)//2} {(y1+y2)//2}")
        raise SystemExit(0)
raise SystemExit(1)
PY
)" || true
    if [[ -n "${coords}" ]]; then
      read -r x y <<<"${coords}"
      echo "${text} => ${x},${y}" | tee "${EVIDENCE_DIR}/self-test-button.txt"
      adb shell input tap "${x}" "${y}"
      return 0
    fi
    adb shell input swipe 540 1600 540 500 350
    sleep 1
  done
  echo "Unable to locate UI text: ${text}" >&2
  return 1
}

find_and_tap "Yerel Self-Test"
sleep 4

adb shell run-as "${PACKAGE}" cat shared_prefs/phone_agent_events.xml > "${EVIDENCE_DIR}/phone_agent_events.xml"
adb shell run-as "${PACKAGE}" cat shared_prefs/phone_agent_self_test.xml > "${EVIDENCE_DIR}/phone_agent_self_test.xml"

adb shell getprop ro.product.manufacturer | tr -d "\r" > "${EVIDENCE_DIR}/manufacturer.txt"
adb shell getprop ro.product.model | tr -d "\r" > "${EVIDENCE_DIR}/model.txt"
adb shell getprop ro.build.version.release | tr -d "\r" > "${EVIDENCE_DIR}/android-release.txt"
adb shell getprop ro.build.version.sdk | tr -d "\r" > "${EVIDENCE_DIR}/android-sdk.txt"

python3 - "${EVIDENCE_DIR}" "${GITHUB_SHA:-UNKNOWN}" "${APK_SHA256}" <<'PY'
import json, pathlib, sys, xml.etree.ElementTree as ET
root = pathlib.Path(sys.argv[1])
head = sys.argv[2]
apk_sha = sys.argv[3]

events_root = ET.parse(root/"phone_agent_events.xml").getroot()
events_node = events_root.find("./string[@name='events']")
events = json.loads(events_node.text if events_node is not None and events_node.text else "[]")

self_root = ET.parse(root/"phone_agent_self_test.xml").getroot()
hit_node = self_root.find("./int[@name='target_hits']")
hits = int(hit_node.attrib.get("value","0")) if hit_node is not None else 0

def has_pass(action):
    return any(e.get("action") == action and e.get("status") == "PASS" for e in events)

service_ready = any(e.get("action") == "SERVICE" and e.get("status") == "READY" for e in events)
tap_pass = has_pass("TAP")
click_pass = has_pass("CLICK_TEXT")
scroll_pass = has_pass("SCROLL_FORWARD")
status = "EMULATOR_PHONE_AGENT_RUNTIME_PASS" if all([service_ready, hits > 0, tap_pass, click_pass, scroll_pass]) else "EMULATOR_PHONE_AGENT_RUNTIME_FAIL"

pkg = (root/"dumpsys-package.txt").read_text(errors="replace")
if "versionName=1.1.1" not in pkg:
    raise SystemExit("versionName mismatch")
if "versionCode=3" not in pkg:
    raise SystemExit("versionCode mismatch")

data = {
    "version": 1,
    "status": status,
    "git_head": head,
    "package_name": "com.example.gptasistan",
    "version_name": "1.1.1",
    "version_code": "3",
    "apk_sha256": apk_sha,
    "device": {
        "manufacturer": (root/"manufacturer.txt").read_text().strip(),
        "model": (root/"model.txt").read_text().strip(),
        "android_release": (root/"android-release.txt").read_text().strip(),
        "android_sdk": (root/"android-sdk.txt").read_text().strip(),
    },
    "accessibility": {
        "service_component": "com.example.gptasistan/com.example.gptasistan.PhoneAgentAccessibilityService",
        "enabled": True,
        "service_ready": service_ready,
    },
    "self_test": {
        "target_hits": hits,
        "tap_pass": tap_pass,
        "click_text_pass": click_pass,
        "scroll_forward_pass": scroll_pass,
    },
    "events": events,
}
(root/"phone-agent-emulator-evidence.json").write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
print(json.dumps(data,sort_keys=True))
if status != "EMULATOR_PHONE_AGENT_RUNTIME_PASS":
    raise SystemExit(30)
PY

(cd "${EVIDENCE_DIR}" && sha256sum *.txt *.xml *.json APK_SHA256 > SHA256SUMS)
(cd "${EVIDENCE_DIR}" && sha256sum -c SHA256SUMS)
cat "${EVIDENCE_DIR}/phone-agent-emulator-evidence.json"
