#!/usr/bin/env python3
import argparse
import copy
import hashlib
import json
import pathlib
import re

TARGET_HEAD = "c8b52661921f82d9e832a0dcf7eed514e970bf49"
PACKAGE_NAME = "com.mehmetcerdik.ownerai"
VERSION_NAME = "1.2.0"
VERSION_CODE = "4"
UNSIGNED_ARTIFACT_SHA256 = "f2066559876b71ae935b2515a81300c197d7308fcc29cbcdff4972f6eae86e44"
EXPECTED_SIGNER_CERT_SHA256 = "279084a36b7c17a1663bfba5fe1c5bdac974f8ef4ce56b21000d882493e39448"
SIGNED_ARTIFACT_SHA256 = None
RUNTIME_IMPLEMENTATION = "v1_accessibility"
REQUIRED_EVENT_ACTIONS = ("TAP", "CLICK_TEXT", "SCROLL_FORWARD")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def canonical_sha256(data):
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def fail(status, **extra):
    payload = {"status": status, **extra}
    print(json.dumps(payload, sort_keys=True))
    raise SystemExit(2)


def require(condition, status, **extra):
    if not condition:
        fail(status, **extra)


def contract(signed_artifact_sha256=SIGNED_ARTIFACT_SHA256):
    return {
        "version": 1,
        "target_head": TARGET_HEAD,
        "package_name": PACKAGE_NAME,
        "version_name": VERSION_NAME,
        "version_code": VERSION_CODE,
        "unsigned_artifact_sha256": UNSIGNED_ARTIFACT_SHA256,
        "expected_signer_cert_sha256": EXPECTED_SIGNER_CERT_SHA256,
        "signed_artifact_sha256": signed_artifact_sha256,
        "phone_agent_runtime": "v1_accessibility_dynamic_evidence",
        "runtime_implementation": RUNTIME_IMPLEMENTATION,
        "required_event_actions": list(REQUIRED_EVENT_ACTIONS),
    }


def validate_data(data, expected=None):
    expected = contract() if expected is None else expected
    signed_hash = expected.get("signed_artifact_sha256")
    require(
        isinstance(signed_hash, str) and HEX64.fullmatch(signed_hash) is not None and signed_hash != "0" * 64,
        "OWNER_SIGNED_RELEASE_NOT_FROZEN",
    )
    require(data.get("version") == 4, "OWNER_REAL_DEVICE_EVIDENCE_SCHEMA_MISMATCH", actual=data.get("version"), expected=4)
    require(data.get("status") == "OWNER_REAL_DEVICE_EVIDENCE_CAPTURED", "OWNER_REAL_DEVICE_CAPTURE_STATUS_INVALID", actual=data.get("status"))
    require(data.get("git_head") == expected["target_head"], "OWNER_REAL_DEVICE_HEAD_MISMATCH", actual=data.get("git_head"), expected=expected["target_head"])

    device = data.get("evidence") or {}
    runtime = data.get("phone_agent") or {}

    checks = {
        "package_name": (str(device.get("package_name", "")), expected["package_name"]),
        "version_name": (str(device.get("version_name", "")), expected["version_name"]),
        "version_code": (str(device.get("version_code", "")), str(expected["version_code"])),
        "source_unsigned_sha256": (str(device.get("source_unsigned_sha256", "")).lower(), expected["unsigned_artifact_sha256"].lower()),
        "artifact_sha256": (str(device.get("artifact_sha256", "")).lower(), signed_hash.lower()),
        "signer_cert_sha256": (str(device.get("signer_cert_sha256", "")).lower(), expected["expected_signer_cert_sha256"].lower()),
    }
    mismatches = {k: {"actual": a, "expected": e} for k, (a, e) in checks.items() if a != e}
    require(not mismatches, "OWNER_REAL_DEVICE_IDENTITY_MISMATCH", mismatches=mismatches)

    for field in ("install_result", "launch_result", "postcondition_result"):
        require(device.get(field) == "PASS", "OWNER_REAL_DEVICE_POSTCONDITION_FAIL", field=field, actual=device.get(field))

    require(runtime.get("implementation") == expected["runtime_implementation"],
            "OWNER_PHONE_AGENT_IMPLEMENTATION_MISMATCH",
            actual=runtime.get("implementation"), expected=expected["runtime_implementation"])
    require(runtime.get("network_permission") == "NONE",
            "OWNER_PHONE_AGENT_NETWORK_POLICY_MISMATCH", actual=runtime.get("network_permission"))
    require(runtime.get("accessibility_enabled") is True, "OWNER_PHONE_AGENT_ACCESSIBILITY_NOT_ENABLED")
    require(runtime.get("service_connected") is True, "OWNER_PHONE_AGENT_SERVICE_NOT_CONNECTED")
    require(int(runtime.get("self_test_target_hits", 0)) > 0,
            "OWNER_PHONE_AGENT_SELF_TEST_TARGET_NOT_HIT", actual=runtime.get("self_test_target_hits"))
    require(runtime.get("tap_pass") is True, "OWNER_PHONE_AGENT_TAP_NOT_VERIFIED")
    require(runtime.get("click_text_pass") is True, "OWNER_PHONE_AGENT_CLICK_TEXT_NOT_VERIFIED")
    require(runtime.get("scroll_forward_pass") is True, "OWNER_PHONE_AGENT_SCROLL_NOT_VERIFIED")
    require(runtime.get("runtime_postcondition_result") == "PASS",
            "OWNER_PHONE_AGENT_RUNTIME_POSTCONDITION_FAIL", actual=runtime.get("runtime_postcondition_result"))

    events = runtime.get("events") or []
    passed = {e.get("action") for e in events if isinstance(e, dict) and e.get("status") == "PASS"}
    missing_events = [a for a in expected["required_event_actions"] if a not in passed]
    require(not missing_events, "OWNER_PHONE_AGENT_EVENT_EVIDENCE_INCOMPLETE", missing=missing_events)
    require(any(isinstance(e, dict) and e.get("action") == "SERVICE" and e.get("status") == "READY" for e in events),
            "OWNER_PHONE_AGENT_SERVICE_READY_EVENT_MISSING")

    return {
        "version": 1,
        "status": "OWNER_REAL_DEVICE_EVIDENCE_VERIFIED",
        "target_head": expected["target_head"],
        "package_name": expected["package_name"],
        "version_name": expected["version_name"],
        "version_code": expected["version_code"],
        "unsigned_artifact_sha256": expected["unsigned_artifact_sha256"],
        "signed_artifact_sha256": signed_hash,
        "signer_cert_sha256": expected["expected_signer_cert_sha256"],
        "device_model": device.get("device_model"),
        "android_version": device.get("android_version"),
        "captured_at_epoch_ms": data.get("captured_at_epoch_ms"),
        "self_test_target_hits": runtime.get("self_test_target_hits"),
        "verified_actions": sorted(expected["required_event_actions"]),
        "evidence_canonical_sha256": canonical_sha256(data),
    }


def validate_file(path):
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return validate_data(data, contract())


def fixture(signed_hash):
    return {
        "version": 4,
        "status": "OWNER_REAL_DEVICE_EVIDENCE_CAPTURED",
        "git_head": TARGET_HEAD,
        "captured_at_epoch_ms": 1790200000000,
        "evidence": {
            "device_model": "CI FIXTURE DEVICE",
            "android_version": "15 (SDK 35)",
            "package_name": PACKAGE_NAME,
            "version_name": VERSION_NAME,
            "version_code": VERSION_CODE,
            "source_unsigned_sha256": UNSIGNED_ARTIFACT_SHA256,
            "artifact_sha256": signed_hash,
            "signer_cert_sha256": EXPECTED_SIGNER_CERT_SHA256,
            "install_result": "PASS",
            "launch_result": "PASS",
            "postcondition_result": "PASS",
        },
        "phone_agent": {
            "implementation": RUNTIME_IMPLEMENTATION,
            "accessibility_enabled": True,
            "service_connected": True,
            "network_permission": "NONE",
            "self_test_target_hits": 2,
            "tap_pass": True,
            "click_text_pass": True,
            "scroll_forward_pass": True,
            "runtime_postcondition_result": "PASS",
            "events": [
                {"timestamp_ms": 1, "action": "SERVICE", "status": "READY", "detail": "fixture"},
                {"timestamp_ms": 2, "action": "TAP", "status": "PASS", "detail": "fixture"},
                {"timestamp_ms": 3, "action": "CLICK_TEXT", "status": "PASS", "detail": "fixture"},
                {"timestamp_ms": 4, "action": "SCROLL_FORWARD", "status": "PASS", "detail": "fixture"},
            ],
        },
    }


def self_test():
    signed_hash = "a" * 64
    expected = contract(signed_hash)
    valid = fixture(signed_hash)
    result = validate_data(valid, expected)
    assert result["status"] == "OWNER_REAL_DEVICE_EVIDENCE_VERIFIED"

    cases = []
    bad = copy.deepcopy(valid)
    bad["evidence"]["artifact_sha256"] = "b" * 64
    cases.append(bad)
    bad = copy.deepcopy(valid)
    bad["evidence"]["signer_cert_sha256"] = "c" * 64
    cases.append(bad)
    bad = copy.deepcopy(valid)
    bad["phone_agent"]["scroll_forward_pass"] = False
    bad["phone_agent"]["runtime_postcondition_result"] = "PENDING"
    bad["phone_agent"]["events"] = [e for e in bad["phone_agent"]["events"] if e["action"] != "SCROLL_FORWARD"]
    cases.append(bad)

    for payload in cases:
        try:
            validate_data(payload, expected)
        except SystemExit:
            pass
        else:
            raise AssertionError("negative fixture unexpectedly accepted")

    try:
        validate_data(valid, contract())
    except SystemExit:
        pass
    else:
        raise AssertionError("production contract unexpectedly accepted without signed artifact hash")

    print(json.dumps({"status": "OWNER_REAL_DEVICE_VERIFIER_SELF_TEST_PASS", "target_head": TARGET_HEAD}, sort_keys=True))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input")
    p.add_argument("--output")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--print-contract", action="store_true")
    args = p.parse_args()

    if args.self_test:
        self_test()
        return
    if args.print_contract:
        print(json.dumps(contract(), sort_keys=True, indent=2))
        return
    if not args.input:
        p.error("--input is required unless --self-test or --print-contract is used")

    result = validate_file(args.input)
    rendered = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output:
        out = pathlib.Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
