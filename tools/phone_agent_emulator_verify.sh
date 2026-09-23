#!/usr/bin/env bash
set -euo pipefail

PACKAGE="com.example.gptasistan"
SERVICE="${PACKAGE}/.PhoneAgentAccessibilityService"
SERVICE_FULL="${PACKAGE}/${PACKAGE}.PhoneAgentAccessibilityService"
APK="${APK_PATH:-app/build/outputs/apk/debug/app-debug.apk}"
EVIDENCE_DIR="${EVIDENCE_DIR:-emulator-evidence}"
mkdir -p "${EVIDENCE_DIR}"

test -f "${APK}"
APK_SHA256="$(sha256sum "${APK}" | awk '{print $1}')"
printf "%s  %s\n" "${APK_SHA256}" "$(basename "${APK}")" > "${EVIDENCE_DIR}/APK_SHA256"

adb wait-for-device
adb install -r "${APK}" | tee "${EVIDENCE_DIR}/adb-install.txt"

adb shell cmd appops set "${PACKAGE}" ACCESS_RESTRICTED_SETTINGS allow || true
adb shell cmd appops get "${PACKAGE}" ACCESS_RESTRICTED_SETTINGS | tee "${EVIDENCE_DIR}/restricted-settings-appop.txt" || true

dump_ui() {
  local out="$1"
  local attempt
  rm -f "${out}"
  for attempt in 1 2 3 4 5; do
    adb shell uiautomator dump /sdcard/window.xml >/dev/null 2>&1 || true
    if adb pull /sdcard/window.xml "${out}" >/dev/null 2>&1 && [[ -s "${out}" ]]; then
      return 0
    fi
    sleep 1
  done
  return 1
}

capture_debug() {
  adb shell settings --user 0 get secure enabled_accessibility_services 2>/dev/null | tr -d "\r" > "${EVIDENCE_DIR}/debug-enabled-accessibility.txt" || true
  adb shell dumpsys accessibility > "${EVIDENCE_DIR}/debug-dumpsys-accessibility.txt" 2>/dev/null || true
  adb exec-out screencap -p > "${EVIDENCE_DIR}/debug-screen.png" 2>/dev/null || true
  dump_ui "${EVIDENCE_DIR}/debug-window.xml" || true
}
trap capture_debug EXIT

tap_text_once() {
  local needle="$1"
  local xml="${EVIDENCE_DIR}/ui-tap.xml"
  local coords
  dump_ui "${xml}" || return 1
  coords="$(python3 - "${xml}" "${needle}" <<'PY'
import re, sys, xml.etree.ElementTree as ET
path, needle = sys.argv[1], sys.argv[2].lower()
root = ET.parse(path).getroot()
candidates = []
for node in root.iter("node"):
    text = (node.attrib.get("text") or "").strip()
    desc = (node.attrib.get("content-desc") or "").strip()
    label = (text + " " + desc).strip()
    if needle not in label.lower():
        continue
    m = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.attrib.get("bounds",""))
    if not m:
        continue
    score = 0
    if text.lower() == needle or desc.lower() == needle:
        score += 100
    if node.attrib.get("clickable") == "true":
        score += 50
    cls = node.attrib.get("class","")
    if cls.endswith("Button") or cls.endswith("Switch"):
        score += 20
    x1,y1,x2,y2 = map(int,m.groups())
    candidates.append((score, (x1+x2)//2, (y1+y2)//2, label))
if not candidates:
    raise SystemExit(1)
candidates.sort(reverse=True)
_, x, y, _ = candidates[0]
print(f"{x} {y}")
PY
)" || true
  [[ -n "${coords}" ]] || return 1
  read -r x y <<<"${coords}"
  adb shell input tap "${x}" "${y}"
  sleep 1
}

scroll_find_and_tap() {
  local needle="$1"
  local attempt
  for attempt in 1 2 3 4 5 6; do
    if tap_text_once "${needle}"; then return 0; fi
    adb shell input swipe 540 1600 540 500 350
    sleep 1
  done
  return 1
}

tap_first_switch() {
  local xml="${EVIDENCE_DIR}/ui-switch.xml"
  local coords
  dump_ui "${xml}" || return 1
  coords="$(python3 - "${xml}" <<'PY'
import re, sys, xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
for node in root.iter("node"):
    cls=node.attrib.get("class","")
    rid=node.attrib.get("resource-id","")
    if "Switch" in cls or "switch_widget" in rid:
        m=re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]",node.attrib.get("bounds",""))
        if m:
            x1,y1,x2,y2=map(int,m.groups())
            print(f"{(x1+x2)//2} {(y1+y2)//2}")
            raise SystemExit(0)
raise SystemExit(1)
PY
)" || true
  [[ -n "${coords}" ]] || return 1
  read -r x y <<<"${coords}"
  adb shell input tap "${x}" "${y}"
  sleep 1
}

ENABLED="$(adb shell settings --user 0 get secure enabled_accessibility_services | tr -d "\r")"
if [[ ":${ENABLED}:" != *":${SERVICE}:"* && ":${ENABLED}:" != *":${SERVICE_FULL}:"* ]]; then
  adb shell am start -W     -a android.settings.ACCESSIBILITY_DETAILS_SETTINGS     --ecn android.provider.extra.ACCESSIBILITY_SERVICE_COMPONENT_NAME "${SERVICE}"     | tee "${EVIDENCE_DIR}/accessibility-details-start.txt" || true
  sleep 3

  if ! tap_first_switch; then
    tap_text_once "Use MEHMET Owner" || tap_text_once "Use service" || true
  fi
  sleep 1
  tap_text_once "Allow" || tap_text_once "OK" || true
  sleep 3

  ENABLED="$(adb shell settings --user 0 get secure enabled_accessibility_services | tr -d "\r")"
  if [[ ":${ENABLED}:" != *":${SERVICE}:"* && ":${ENABLED}:" != *":${SERVICE_FULL}:"* ]]; then
    adb shell am start -W -a android.settings.ACCESSIBILITY_SETTINGS       | tee "${EVIDENCE_DIR}/accessibility-settings-start.txt" || true
    sleep 3

    if ! scroll_find_and_tap "MEHMET Owner"; then
      for group in "Downloaded apps" "Installed apps" "Downloaded services" "Installed services"; do
        if scroll_find_and_tap "${group}"; then
          sleep 2
          break
        fi
      done
      scroll_find_and_tap "MEHMET Owner" || true
    fi

    sleep 2
    if ! tap_first_switch; then
      tap_text_once "Use MEHMET Owner" || tap_text_once "Use service" || true
    fi
    sleep 1
    tap_text_once "Allow" || tap_text_once "OK" || true
    sleep 3
  fi
fi

ENABLED="$(adb shell settings --user 0 get secure enabled_accessibility_services | tr -d "\r")"
printf "%s\n" "${ENABLED}" > "${EVIDENCE_DIR}/enabled_accessibility_services.txt"
case ":${ENABLED}:" in
  *":${SERVICE}:"*|*":${SERVICE_FULL}:"*) ;;
  *) echo "Expected accessibility service is not enabled after Settings UI flow: ${ENABLED}" >&2; exit 20 ;;
esac

for attempt in 1 2 3 4 5; do
  adb shell dumpsys accessibility > "${EVIDENCE_DIR}/prelaunch-dumpsys-accessibility.txt"
  if grep -q "PhoneAgentAccessibilityService" "${EVIDENCE_DIR}/prelaunch-dumpsys-accessibility.txt"; then
    break
  fi
  sleep 1
done

# Do not force-stop here: on Android 14 the force-stop can tear down the
# freshly consented accessibility service and clear the enabled-service state.
adb shell am start -W -n "${PACKAGE}/com.example.gptasistan.MainActivity" --ez emulator_self_test true | tee "${EVIDENCE_DIR}/am-start.txt"
sleep 7

adb shell dumpsys accessibility > "${EVIDENCE_DIR}/dumpsys-accessibility.txt"
adb shell dumpsys package "${PACKAGE}" > "${EVIDENCE_DIR}/dumpsys-package.txt"
grep -q "PhoneAgentAccessibilityService" "${EVIDENCE_DIR}/dumpsys-accessibility.txt"

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
if "versionName=1.2.0" not in pkg:
    raise SystemExit("versionName mismatch")
if "versionCode=4" not in pkg:
    raise SystemExit("versionCode mismatch")

data = {
    "version": 1,
    "status": status,
    "git_head": head,
    "package_name": "com.mehmetcerdik.ownerai",
    "version_name": "1.2.0",
    "version_code": "4",
    "apk_sha256": apk_sha,
    "device": {
        "manufacturer": (root/"manufacturer.txt").read_text().strip(),
        "model": (root/"model.txt").read_text().strip(),
        "android_release": (root/"android-release.txt").read_text().strip(),
        "android_sdk": (root/"android-sdk.txt").read_text().strip(),
    },
    "accessibility": {
        "service_component": "com.mehmetcerdik.ownerai/com.example.gptasistan.PhoneAgentAccessibilityService",
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
