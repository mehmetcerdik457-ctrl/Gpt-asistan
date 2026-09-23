#!/usr/bin/env python3
import argparse
import copy
import hashlib
import json
import pathlib
import re

OWNER_SOURCE_HEAD = "c8b52661921f82d9e832a0dcf7eed514e970bf49"
OWNER_PACKAGE = "com.mehmetcerdik.ownerai"
OWNER_VERSION_NAME = "1.2.0"
OWNER_VERSION_CODE = "4"
OWNER_SIGNED_SHA256 = "55a179f96811671430556c99ee747280d648ead6833eaf7419009b4214be5394"

BRIDGE_SOURCE_ZIP_SHA256 = "7df6d150b9159affe69e529fdf1ada3ce8f957ffb1c99ba7c55f8fe3eefd7628"
BRIDGE_PACKAGE = "com.mehmetcerdik.ownerbridge"
BRIDGE_VERSION_NAME = "1.1.0"
BRIDGE_VERSION_CODE = "2"
BRIDGE_BUILD_HEAD = "2f8331d4b2864cd0224cb33ff33841cd27c811c7"
BRIDGE_UNSIGNED_SHA256 = "1f096c7fdfd0d02a823e99b86a5dda10f281c08cd31a077400c771c81516a4d8"
BRIDGE_SIGNED_SHA256 = "525987419b4bda071794833b12c7423df7584a30c1b609d00ed324d85d2a883a"

GEN2_SIGNER_SHA256 = "279084a36b7c17a1663bfba5fe1c5bdac974f8ef4ce56b21000d882493e39448"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")


def canonical_sha256(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def fail(status, **extra):
    print(json.dumps({"status": status, **extra}, sort_keys=True))
    raise SystemExit(2)


def require(cond, status, **extra):
    if not cond:
        fail(status, **extra)


def contract(verifier_head):
    require(isinstance(verifier_head, str) and HEX40.fullmatch(verifier_head), "FULL_VERIFIER_HEAD_INVALID")
    return {
        "version": 1,
        "accept_status": "FULL_REAL_DEVICE_EVIDENCE_VERIFIED",
        "verifier_head": verifier_head,
        "owner": {
            "source_head": OWNER_SOURCE_HEAD,
            "package_name": OWNER_PACKAGE,
            "version_name": OWNER_VERSION_NAME,
            "version_code": OWNER_VERSION_CODE,
            "signed_artifact_sha256": OWNER_SIGNED_SHA256,
            "signer_cert_sha256": GEN2_SIGNER_SHA256,
        },
        "bridge": {
            "source_zip_sha256": BRIDGE_SOURCE_ZIP_SHA256,
            "package_name": BRIDGE_PACKAGE,
            "version_name": BRIDGE_VERSION_NAME,
            "version_code": BRIDGE_VERSION_CODE,
            "unsigned_artifact_sha256": BRIDGE_UNSIGNED_SHA256,
            "signed_artifact_sha256": BRIDGE_SIGNED_SHA256,
            "signer_cert_sha256": GEN2_SIGNER_SHA256,
            "network_permission": "NONE",
        },
        "required_runtime": [
            "OWNER_TAP",
            "BRIDGE_LAUNCH_APP",
            "BRIDGE_SWIPE",
            "BRIDGE_TYPE_TEXT",
            "POSTCONDITION",
            "AUDIT_RECORD",
        ],
    }


def event_has(events, action, statuses):
    statuses = {statuses} if isinstance(statuses, str) else set(statuses)
    return any(
        isinstance(e, dict)
        and e.get("action") == action
        and e.get("status") in statuses
        for e in (events or [])
    )


def validate_owner(data, expected):
    require(data.get("version") == 3, "FULL_OWNER_SCHEMA_MISMATCH", actual=data.get("version"), expected=3)
    require(data.get("status") == "REAL_DEVICE_EVIDENCE_CAPTURED",
            "FULL_OWNER_CAPTURE_STATUS_INVALID", actual=data.get("status"))
    require(data.get("git_head") == expected["source_head"],
            "FULL_OWNER_SOURCE_HEAD_MISMATCH", actual=data.get("git_head"), expected=expected["source_head"])

    device = data.get("evidence") or {}
    runtime = data.get("phone_agent") or {}
    checks = {
        "package_name": (str(device.get("package_name", "")), expected["package_name"]),
        "version_name": (str(device.get("version_name", "")), expected["version_name"]),
        "version_code": (str(device.get("version_code", "")), expected["version_code"]),
        "artifact_sha256": (str(device.get("artifact_sha256", "")).lower(), expected["signed_artifact_sha256"]),
        "signer_cert_sha256": (str(device.get("signer_cert_sha256", "")).lower(), expected["signer_cert_sha256"]),
        "bridge_signer_cert_sha256": (str(device.get("bridge_signer_cert_sha256", "")).lower(), expected["signer_cert_sha256"]),
    }
    mismatches = {k: {"actual": a, "expected": e} for k, (a, e) in checks.items() if a != e}
    require(not mismatches, "FULL_OWNER_IDENTITY_MISMATCH", mismatches=mismatches)
    require(device.get("bridge_signer_match") is True, "FULL_OWNER_BRIDGE_SIGNER_NOT_MATCHED")

    for field in ("install_result", "launch_result", "postcondition_result"):
        require(device.get(field) == "PASS", "FULL_OWNER_DEVICE_RESULT_FAIL", field=field, actual=device.get(field))

    require(runtime.get("network_permission") == "NONE", "FULL_OWNER_NETWORK_POLICY_MISMATCH")
    require(runtime.get("accessibility_enabled") is True, "FULL_OWNER_ACCESSIBILITY_NOT_ENABLED")
    require(runtime.get("service_connected") is True, "FULL_OWNER_SERVICE_NOT_CONNECTED")
    require(int(runtime.get("self_test_target_hits", 0)) > 0, "FULL_OWNER_SELF_TEST_TARGET_NOT_HIT")
    require(runtime.get("tap_pass") is True, "FULL_OWNER_TAP_NOT_VERIFIED")
    require(runtime.get("runtime_postcondition_result") == "PASS", "FULL_OWNER_RUNTIME_POSTCONDITION_FAIL")
    require(event_has(runtime.get("events"), "TAP", "PASS"), "FULL_OWNER_TAP_EVENT_MISSING")
    return {
        "device_model": device.get("device_model"),
        "android_version": device.get("android_version"),
        "captured_at_epoch_ms": data.get("captured_at_epoch_ms"),
    }


def validate_bridge(data, expected_bridge, expected_owner):
    require(data.get("version") == 1, "FULL_BRIDGE_SCHEMA_MISMATCH", actual=data.get("version"), expected=1)
    require(data.get("status") == "FULL_BRIDGE_EVIDENCE_CAPTURED",
            "FULL_BRIDGE_CAPTURE_STATUS_INVALID", actual=data.get("status"))
    require(str(data.get("source_zip_sha256", "")).lower() == expected_bridge["source_zip_sha256"],
            "FULL_BRIDGE_SOURCE_LINEAGE_MISMATCH")

    bridge = data.get("bridge") or {}
    installed_owner = data.get("owner") or {}
    runtime = data.get("runtime") or {}

    bridge_checks = {
        "package_name": (str(bridge.get("package_name", "")), expected_bridge["package_name"]),
        "version_name": (str(bridge.get("version_name", "")), expected_bridge["version_name"]),
        "version_code": (str(bridge.get("version_code", "")), expected_bridge["version_code"]),
        "artifact_sha256": (str(bridge.get("artifact_sha256", "")).lower(), expected_bridge["signed_artifact_sha256"]),
        "signer_cert_sha256": (str(bridge.get("signer_cert_sha256", "")).lower(), expected_bridge["signer_cert_sha256"]),
        "network_permission": (str(bridge.get("network_permission", "")), "NONE"),
    }
    mismatches = {k: {"actual": a, "expected": e} for k, (a, e) in bridge_checks.items() if a != e}
    require(not mismatches, "FULL_BRIDGE_IDENTITY_MISMATCH", mismatches=mismatches)
    require(bridge.get("package_match") is True and bridge.get("version_match") is True and bridge.get("signer_match") is True,
            "FULL_BRIDGE_SELF_IDENTITY_FLAGS_FAIL")
    require(bridge.get("accessibility_enabled") is True, "FULL_BRIDGE_ACCESSIBILITY_NOT_ENABLED")
    require(bridge.get("service_connected") is True, "FULL_BRIDGE_SERVICE_NOT_CONNECTED")
    require(bridge.get("emergency_stop") is False, "FULL_BRIDGE_EMERGENCY_STOP_ACTIVE")

    owner_checks = {
        "installed": (installed_owner.get("installed"), True),
        "package_name": (str(installed_owner.get("package_name", "")), expected_owner["package_name"]),
        "version_name": (str(installed_owner.get("version_name", "")), expected_owner["version_name"]),
        "version_code": (str(installed_owner.get("version_code", "")), expected_owner["version_code"]),
        "artifact_sha256": (str(installed_owner.get("artifact_sha256", "")).lower(), expected_owner["signed_artifact_sha256"]),
        "signer_cert_sha256": (str(installed_owner.get("signer_cert_sha256", "")).lower(), expected_owner["signer_cert_sha256"]),
    }
    owner_mismatches = {k: {"actual": a, "expected": e} for k, (a, e) in owner_checks.items() if a != e}
    require(not owner_mismatches, "FULL_BRIDGE_OBSERVED_OWNER_IDENTITY_MISMATCH", mismatches=owner_mismatches)

    require(runtime.get("audit_integrity") is True, "FULL_BRIDGE_AUDIT_INTEGRITY_FAIL",
            reason=runtime.get("audit_integrity_reason"))
    require(int(runtime.get("audit_records", 0)) > 0, "FULL_BRIDGE_AUDIT_EMPTY")
    require(runtime.get("launch_pass") is True, "FULL_BRIDGE_LAUNCH_NOT_VERIFIED")
    require(runtime.get("swipe_pass") is True, "FULL_BRIDGE_SWIPE_NOT_VERIFIED")
    require(runtime.get("type_pass") is True, "FULL_BRIDGE_TYPE_NOT_VERIFIED")
    require(runtime.get("postcondition_pass") is True, "FULL_BRIDGE_POSTCONDITION_NOT_VERIFIED")
    require(runtime.get("record_pass") is True, "FULL_BRIDGE_RECORD_NOT_VERIFIED")

    events = runtime.get("events") or []
    require(event_has(events, "LAUNCH_APP", "TARGET_POSTCONDITION_CONFIRMED"),
            "FULL_BRIDGE_LAUNCH_EVENT_MISSING")
    require(event_has(events, "SWIPE", ("GESTURE_COMPLETED", "UI_CHANGED", "TARGET_POSTCONDITION_CONFIRMED")),
            "FULL_BRIDGE_SWIPE_EVENT_MISSING")
    require(event_has(events, "TYPE_TEXT", "TARGET_POSTCONDITION_CONFIRMED"),
            "FULL_BRIDGE_TYPE_EVENT_MISSING")

    return {
        "captured_at_epoch_ms": data.get("captured_at_epoch_ms"),
        "audit_records": runtime.get("audit_records"),
    }


def validate(owner_data, bridge_data, verifier_head):
    c = contract(verifier_head)
    owner_meta = validate_owner(owner_data, c["owner"])
    bridge_meta = validate_bridge(bridge_data, c["bridge"], c["owner"])
    return {
        "version": 1,
        "status": c["accept_status"],
        "verifier_head": verifier_head,
        "owner_source_head": c["owner"]["source_head"],
        "owner_signed_artifact_sha256": c["owner"]["signed_artifact_sha256"],
        "owner_signer_cert_sha256": c["owner"]["signer_cert_sha256"],
        "bridge_source_zip_sha256": c["bridge"]["source_zip_sha256"],
        "bridge_unsigned_artifact_sha256": c["bridge"]["unsigned_artifact_sha256"],
        "bridge_signed_artifact_sha256": c["bridge"]["signed_artifact_sha256"],
        "bridge_signer_cert_sha256": c["bridge"]["signer_cert_sha256"],
        "device_model": owner_meta.get("device_model"),
        "android_version": owner_meta.get("android_version"),
        "owner_evidence_canonical_sha256": canonical_sha256(owner_data),
        "bridge_evidence_canonical_sha256": canonical_sha256(bridge_data),
        "verified_runtime": c["required_runtime"],
        "bridge_audit_records": bridge_meta.get("audit_records"),
    }


def owner_fixture():
    return {
        "version": 3,
        "status": "REAL_DEVICE_EVIDENCE_CAPTURED",
        "git_head": OWNER_SOURCE_HEAD,
        "captured_at_epoch_ms": 1,
        "evidence": {
            "device_model": "CI FIXTURE",
            "android_version": "15 (SDK 35)",
            "package_name": OWNER_PACKAGE,
            "version_name": OWNER_VERSION_NAME,
            "version_code": OWNER_VERSION_CODE,
            "artifact_sha256": OWNER_SIGNED_SHA256,
            "signer_cert_sha256": GEN2_SIGNER_SHA256,
            "bridge_signer_cert_sha256": GEN2_SIGNER_SHA256,
            "bridge_signer_match": True,
            "install_result": "PASS",
            "launch_result": "PASS",
            "postcondition_result": "PASS",
        },
        "phone_agent": {
            "network_permission": "NONE",
            "accessibility_enabled": True,
            "service_connected": True,
            "self_test_target_hits": 1,
            "tap_pass": True,
            "click_text_pass": True,
            "scroll_forward_pass": True,
            "runtime_postcondition_result": "PASS",
            "events": [
                {"action": "SERVICE", "status": "READY"},
                {"action": "TAP", "status": "PASS"},
                {"action": "CLICK_TEXT", "status": "PASS"},
                {"action": "SCROLL_FORWARD", "status": "PASS"},
            ],
        },
    }


def bridge_fixture():
    return {
        "version": 1,
        "status": "FULL_BRIDGE_EVIDENCE_CAPTURED",
        "source_zip_sha256": BRIDGE_SOURCE_ZIP_SHA256,
        "captured_at_epoch_ms": 2,
        "bridge": {
            "package_name": BRIDGE_PACKAGE,
            "version_name": BRIDGE_VERSION_NAME,
            "version_code": BRIDGE_VERSION_CODE,
            "artifact_sha256": BRIDGE_SIGNED_SHA256,
            "signer_cert_sha256": GEN2_SIGNER_SHA256,
            "package_match": True,
            "version_match": True,
            "signer_match": True,
            "network_permission": "NONE",
            "accessibility_enabled": True,
            "service_connected": True,
            "armed": True,
            "emergency_stop": False,
        },
        "owner": {
            "installed": True,
            "package_name": OWNER_PACKAGE,
            "version_name": OWNER_VERSION_NAME,
            "version_code": 4,
            "artifact_sha256": OWNER_SIGNED_SHA256,
            "signer_cert_sha256": GEN2_SIGNER_SHA256,
        },
        "runtime": {
            "launch_pass": True,
            "swipe_pass": True,
            "type_pass": True,
            "postcondition_pass": True,
            "record_pass": True,
            "audit_integrity": True,
            "audit_integrity_reason": "OK",
            "audit_records": 9,
            "events": [
                {"action": "LAUNCH_APP", "status": "TARGET_POSTCONDITION_CONFIRMED"},
                {"action": "SWIPE", "status": "UI_CHANGED"},
                {"action": "TYPE_TEXT", "status": "TARGET_POSTCONDITION_CONFIRMED"},
            ],
        },
    }


def self_test():
    h = "a" * 40
    owner = owner_fixture()
    bridge = bridge_fixture()
    result = validate(owner, bridge, h)
    assert result["status"] == "FULL_REAL_DEVICE_EVIDENCE_VERIFIED"

    negative = []

    x = copy.deepcopy(owner)
    x["evidence"]["artifact_sha256"] = "b" * 64
    negative.append(("owner_hash", x, bridge))

    x = copy.deepcopy(bridge)
    x["bridge"]["artifact_sha256"] = "c" * 64
    negative.append(("bridge_hash", owner, x))

    x = copy.deepcopy(bridge)
    x["bridge"]["signer_cert_sha256"] = "d" * 64
    negative.append(("bridge_signer", owner, x))

    x = copy.deepcopy(bridge)
    x["runtime"]["swipe_pass"] = False
    x["runtime"]["events"] = [e for e in x["runtime"]["events"] if e["action"] != "SWIPE"]
    negative.append(("swipe", owner, x))

    x = copy.deepcopy(bridge)
    x["runtime"]["type_pass"] = False
    x["runtime"]["postcondition_pass"] = False
    negative.append(("type_postcondition", owner, x))

    x = copy.deepcopy(bridge)
    x["runtime"]["audit_integrity"] = False
    x["runtime"]["record_pass"] = False
    negative.append(("audit", owner, x))

    for name, o, b in negative:
        try:
            validate(o, b, h)
        except SystemExit:
            pass
        else:
            raise AssertionError(name + " negative fixture unexpectedly accepted")

    print(json.dumps({
        "status": "FULL_FINAL_VERIFIER_SELF_TEST_PASS",
        "owner_hash": OWNER_SIGNED_SHA256,
        "bridge_hash": BRIDGE_SIGNED_SHA256,
    }, sort_keys=True))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--owner")
    p.add_argument("--bridge")
    p.add_argument("--output")
    p.add_argument("--verifier-head")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--print-contract", action="store_true")
    args = p.parse_args()

    if args.self_test:
        self_test()
        return
    if args.print_contract:
        if not args.verifier_head:
            p.error("--verifier-head required")
        print(json.dumps(contract(args.verifier_head), sort_keys=True, indent=2))
        return
    if not args.owner or not args.bridge or not args.verifier_head:
        p.error("--owner, --bridge and --verifier-head are required")

    owner_data = json.loads(pathlib.Path(args.owner).read_text(encoding="utf-8"))
    bridge_data = json.loads(pathlib.Path(args.bridge).read_text(encoding="utf-8"))
    result = validate(owner_data, bridge_data, args.verifier_head)
    rendered = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output:
        pathlib.Path(args.output).write_text(rendered, encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
