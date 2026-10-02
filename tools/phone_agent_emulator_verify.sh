#!/usr/bin/env bash
set -euo pipefail

PACKAGE="com.mehmetcerdik.ownerai"
BRIDGE_PACKAGE="com.mehmetcerdik.ownerbridge"
WORKER_PACKAGE="com.codespaceapps.aichat"
CLASS_PACKAGE="com.example.gptasistan"
SERVICE="${PACKAGE}/${CLASS_PACKAGE}.PhoneAgentAccessibilityService"
SERVICE_FULL="${SERVICE}"
MAIN_ACTIVITY="${PACKAGE}/${CLASS_PACKAGE}.MainActivity"
APK="${APK_PATH:-app/build/outputs/apk/debug/app-debug.apk}"
BRIDGE_APK="${BRIDGE_APK_PATH:-bridge/build/outputs/apk/debug/bridge-debug.apk}"
EVIDENCE_DIR="${EVIDENCE_DIR:-emulator-evidence}"
mkdir -p "${EVIDENCE_DIR}"

test -f "${APK}"
APK_SHA256="$(sha256sum "${APK}" | awk '{print $1}')"
printf "%s  %s\n" "${APK_SHA256}" "$(basename "${APK}")" > "${EVIDENCE_DIR}/APK_SHA256"

adb wait-for-device

if [[ -n "${VERIFIER_APKSIGNER:-}" ]]; then
  APKSIGNER="${VERIFIER_APKSIGNER}"
else
  BUILD_TOOLS_VERSION="$(ls "${ANDROID_HOME}/build-tools" | sort -V | tail -1)"
  APKSIGNER="${ANDROID_HOME}/build-tools/${BUILD_TOOLS_VERSION}/apksigner"
fi
test -x "${APKSIGNER}"

package_state() {
  local pkg="$1" label="$2"
  local out="${EVIDENCE_DIR}/${label}"
  mkdir -p "${out}"
  adb shell dumpsys package "${pkg}" > "${out}/dumpsys.txt" 2>/dev/null || true
  adb shell pm path "${pkg}" 2>/dev/null | tr -d "\r" > "${out}/pm-path.txt" || true
  {
    echo "package=${pkg}"
    grep -m1 -E 'versionCode=' "${out}/dumpsys.txt" || true
    grep -m1 -E 'versionName=' "${out}/dumpsys.txt" || true
    grep -m1 -E 'dataDir=' "${out}/dumpsys.txt" || true
    grep -m1 -E 'firstInstallTime=' "${out}/dumpsys.txt" || true
    grep -m1 -E 'lastUpdateTime=' "${out}/dumpsys.txt" || true
  } > "${out}/package-summary.txt"
  local remote
  remote="$(sed -n 's/^package://p' "${out}/pm-path.txt" | head -1)"
  if [[ -n "${remote}" ]]; then
    if adb pull "${remote}" "${out}/installed-base.apk" >/dev/null 2>&1; then
      sha256sum "${out}/installed-base.apk" > "${out}/installed-base.sha256"
      "${APKSIGNER}" verify --print-certs "${out}/installed-base.apk" > "${out}/signer.txt" 2>&1 || true
    fi
  fi
}

candidate_signer() {
  local certs
  certs="$("${APKSIGNER}" verify --print-certs "$1" 2>/dev/null)" || return 1
  printf '%s\n' "${certs}" | sed -nE 's/^.*certificate SHA-256 digest:[[:space:]]*//p' | sed -n '1p' | tr 'A-F' 'a-f'
}

safe_install() {
  local pkg="$1" apk="$2" log="$3"
  test -f "${apk}"
  local candidate existing remote pulled
  candidate="$(candidate_signer "${apk}")"
  [[ "${candidate}" =~ ^[0-9a-f]{64}$ ]] || { echo "FAIL:CANDIDATE_SIGNER_UNREADABLE:${pkg}" >&2; exit 17; }
  remote="$(adb shell pm path "${pkg}" 2>/dev/null | tr -d "\r" | sed -n 's/^package://p' | head -1 || true)"
  if [[ -n "${remote}" ]]; then
    pulled="${EVIDENCE_DIR}/preinstall-${pkg}.apk"
    adb pull "${remote}" "${pulled}" >/dev/null
    existing="$(candidate_signer "${pulled}")"
    if [[ "${existing}" != "${candidate}" ]]; then
      printf 'package=%s\ninstalled_signer=%s\ncandidate_signer=%s\n' "${pkg}" "${existing}" "${candidate}" | tee "${EVIDENCE_DIR}/SIGNER_CONFLICT.txt"
      echo "FAIL:EXACT_SIGNER_CONFLICT_NO_INSTALL_NO_UNINSTALL:${pkg}" >&2
      exit 18
    fi
  fi
  adb install -r "${apk}" | tee "${EVIDENCE_DIR}/${log}"
}

package_state "${PACKAGE}" "before-owner"
package_state "${BRIDGE_PACKAGE}" "before-bridge"
package_state "${WORKER_PACKAGE}" "before-public-cihat"

if [[ -f "${BRIDGE_APK}" ]]; then
  safe_install "${BRIDGE_PACKAGE}" "${BRIDGE_APK}" "adb-install-bridge.txt"
fi
safe_install "${PACKAGE}" "${APK}" "adb-install-owner.txt"

package_state "${PACKAGE}" "after-owner"
package_state "${BRIDGE_PACKAGE}" "after-bridge"
package_state "${WORKER_PACKAGE}" "after-public-cihat"

BEFORE_CIHAT_SHA_FILE="${EVIDENCE_DIR}/before-public-cihat/installed-base.sha256"
AFTER_CIHAT_SHA_FILE="${EVIDENCE_DIR}/after-public-cihat/installed-base.sha256"
BEFORE_CIHAT_PRESENT=0
AFTER_CIHAT_PRESENT=0
[[ -f "${BEFORE_CIHAT_SHA_FILE}" ]] && BEFORE_CIHAT_PRESENT=1
[[ -f "${AFTER_CIHAT_SHA_FILE}" ]] && AFTER_CIHAT_PRESENT=1
if [[ "${BEFORE_CIHAT_PRESENT}" != "${AFTER_CIHAT_PRESENT}" ]]; then
  echo "FAIL:PUBLIC_CIHAT_INSTALL_STATE_CHANGED" >&2
  exit 19
fi
if [[ -f "${BEFORE_CIHAT_SHA_FILE}" && -f "${AFTER_CIHAT_SHA_FILE}" ]]; then
  BEFORE_CIHAT_SHA="$(awk '{print $1}' "${BEFORE_CIHAT_SHA_FILE}")"
  AFTER_CIHAT_SHA="$(awk '{print $1}' "${AFTER_CIHAT_SHA_FILE}")"
  printf 'before_sha256=%s\nafter_sha256=%s\n' "${BEFORE_CIHAT_SHA}" "${AFTER_CIHAT_SHA}" > "${EVIDENCE_DIR}/public-cihat-sha-compare.txt"
  if [[ "${BEFORE_CIHAT_SHA}" != "${AFTER_CIHAT_SHA}" ]]; then
    echo "FAIL:PUBLIC_CIHAT_CHANGED" >&2
    exit 19
  fi
fi

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
    tap_text_once "Use MEHMET Owner Companion" || tap_text_once "Use service" || true
  fi
  sleep 1
  tap_text_once "Allow" || tap_text_once "OK" || true
  sleep 3

  ENABLED="$(adb shell settings --user 0 get secure enabled_accessibility_services | tr -d "\r")"
  if [[ ":${ENABLED}:" != *":${SERVICE}:"* && ":${ENABLED}:" != *":${SERVICE_FULL}:"* ]]; then
    adb shell am start -W -a android.settings.ACCESSIBILITY_SETTINGS       | tee "${EVIDENCE_DIR}/accessibility-settings-start.txt" || true
    sleep 3

    if ! scroll_find_and_tap "MEHMET Owner Companion"; then
      for group in "Downloaded apps" "Installed apps" "Downloaded services" "Installed services"; do
        if scroll_find_and_tap "${group}"; then
          sleep 2
          break
        fi
      done
      scroll_find_and_tap "MEHMET Owner Companion" || true
    fi

    sleep 2
    if ! tap_first_switch; then
      tap_text_once "Use MEHMET Owner Companion" || tap_text_once "Use service" || true
    fi
    sleep 1
    tap_text_once "Allow" || tap_text_once "OK" || true
    sleep 3
  fi
fi

# Android 14+ emulator images may deny shell launch of
# ACCESSIBILITY_DETAILS_SETTINGS with OPEN_ACCESSIBILITY_DETAILS_SETTINGS.
# For CI only, use the shell's secure-settings capability as a deterministic
# fallback. This path is guarded by ro.kernel.qemu=1 and is never used on a
# physical device or in application production code.
ENABLED="$(adb shell settings --user 0 get secure enabled_accessibility_services | tr -d "\r")"
if [[ ":${ENABLED}:" != *":${SERVICE}:"* && ":${ENABLED}:" != *":${SERVICE_FULL}:"* ]]; then
  QEMU="$(adb shell getprop ro.kernel.qemu | tr -d "\r")"
  printf "ro.kernel.qemu=%s\n" "${QEMU}" > "${EVIDENCE_DIR}/accessibility-enable-fallback.txt"
  if [[ "${QEMU}" == "1" ]]; then
    adb shell settings --user 0 put secure enabled_accessibility_services "${SERVICE}"
    adb shell settings --user 0 put secure accessibility_enabled 1
    sleep 3
    adb shell settings --user 0 get secure enabled_accessibility_services | tr -d "\r" >> "${EVIDENCE_DIR}/accessibility-enable-fallback.txt"
  fi
fi

BRIDGE_SERVICE="${BRIDGE_PACKAGE}/.BridgeAccessibilityService"
QEMU="$(adb shell getprop ro.kernel.qemu | tr -d "\r")"
if [[ "${QEMU}" == "1" && -f "${BRIDGE_APK}" ]]; then
  ENABLED_NOW="$(adb shell settings --user 0 get secure enabled_accessibility_services | tr -d "\r")"
  if [[ ":${ENABLED_NOW}:" != *":${BRIDGE_SERVICE}:"* ]]; then
    if [[ -z "${ENABLED_NOW}" || "${ENABLED_NOW}" == "null" ]]; then
      ENABLED_NOW="${BRIDGE_SERVICE}"
    else
      ENABLED_NOW="${ENABLED_NOW}:${BRIDGE_SERVICE}"
    fi
    adb shell settings --user 0 put secure enabled_accessibility_services "${ENABLED_NOW}"
    adb shell settings --user 0 put secure accessibility_enabled 1
    sleep 2
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
adb shell am start -W -n "${MAIN_ACTIVITY}" --ez emulator_self_test true | tee "${EVIDENCE_DIR}/am-start.txt"
sleep 2

# Trigger through the debug-only intent path. MainActivity waits for the local
# debug Accessibility service; Bridge screen-read has its own bounded retry.
# No coordinate/UI-button tap is used for the CI trigger.
sleep 12

adb shell dumpsys accessibility > "${EVIDENCE_DIR}/dumpsys-accessibility.txt"
adb shell dumpsys package "${PACKAGE}" > "${EVIDENCE_DIR}/dumpsys-package.txt"

RUNTIME_PRESENCE_FILE="${EVIDENCE_DIR}/runtime-evidence-presence.txt"
: > "${RUNTIME_PRESENCE_FILE}"
if grep -q "PhoneAgentAccessibilityService" "${EVIDENCE_DIR}/dumpsys-accessibility.txt"; then
  echo "local_accessibility_service=present" >> "${RUNTIME_PRESENCE_FILE}"
else
  echo "local_accessibility_service=missing" >> "${RUNTIME_PRESENCE_FILE}"
fi

collect_pref() {
  local remote="$1" local_name="$2" fallback="$3"
  if adb shell run-as "${PACKAGE}" cat "${remote}" > "${EVIDENCE_DIR}/${local_name}" 2>/dev/null; then
    echo "${local_name}=present" >> "${RUNTIME_PRESENCE_FILE}"
  else
    printf '%s\n' "${fallback}" > "${EVIDENCE_DIR}/${local_name}"
    echo "${local_name}=missing" >> "${RUNTIME_PRESENCE_FILE}"
  fi
}

collect_pref "shared_prefs/phone_agent_events.xml" "phone_agent_events.xml" '<map><string name="events">[]</string></map>'
collect_pref "shared_prefs/phone_agent_self_test.xml" "phone_agent_self_test.xml" '<map />'
collect_pref "shared_prefs/bridge_self_test.xml" "bridge_self_test.xml" '<map />'

adb shell getprop ro.product.manufacturer | tr -d "\r" > "${EVIDENCE_DIR}/manufacturer.txt"
adb shell getprop ro.product.model | tr -d "\r" > "${EVIDENCE_DIR}/model.txt"
adb shell getprop ro.build.version.release | tr -d "\r" > "${EVIDENCE_DIR}/android-release.txt"
adb shell getprop ro.build.version.sdk | tr -d "\r" > "${EVIDENCE_DIR}/android-sdk.txt"

python3 - "${EVIDENCE_DIR}" "${EXPECTED_HEAD_SHA:-${GITHUB_SHA:-UNKNOWN}}" "${APK_SHA256}" <<'PY'
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
bridge_root = ET.parse(root/"bridge_self_test.xml").getroot()
def pref_bool(name):
    n = bridge_root.find("./boolean[@name='%s']" % name)
    return n is not None and n.attrib.get("value") == "true"
bridge_signer = pref_bool("signer_match")
bridge_arm = pref_bool("arm_ok")
bridge_core = pref_bool("core_ok")
bridge_service = pref_bool("service_connected")
bridge_read = pref_bool("screen_read_ok")
status = "EMULATOR_HARDENED_RUNTIME_PASS" if all([
    service_ready, hits > 0, tap_pass, click_pass, scroll_pass,
    bridge_signer, bridge_arm, bridge_core, bridge_service, bridge_read
]) else "EMULATOR_HARDENED_RUNTIME_FAIL"

pkg = (root/"dumpsys-package.txt").read_text(errors="replace")
if "versionName=1.5.1" not in pkg:
    raise SystemExit("versionName mismatch")
if "versionCode=9" not in pkg:
    raise SystemExit("versionCode mismatch")

data = {
    "version": 1,
    "status": status,
    "git_head": head,
    "package_name": "com.mehmetcerdik.ownerai",
    "version_name": "1.5.1",
    "version_code": "9",
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
    "bridge": {
        "signer_match": bridge_signer,
        "arm_ok": bridge_arm,
        "core_ok": bridge_core,
        "service_connected": bridge_service,
        "screen_read_ok": bridge_read,
    },
    "events": events,
}
(root/"phone-agent-emulator-evidence.json").write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
print(json.dumps(data,sort_keys=True))
if status != "EMULATOR_HARDENED_RUNTIME_PASS":
    raise SystemExit(30)
PY

(cd "${EVIDENCE_DIR}" && sha256sum *.txt *.xml *.json APK_SHA256 > SHA256SUMS)
(cd "${EVIDENCE_DIR}" && sha256sum -c SHA256SUMS)
cat "${EVIDENCE_DIR}/phone-agent-emulator-evidence.json"
