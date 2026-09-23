#!/usr/bin/env python3
import argparse
import hashlib
import json
import pathlib
import re

HEX64 = re.compile(r"^[0-9a-f]{64}$")

def fail(status, **extra):
    payload = {"status": status, **extra}
    print(json.dumps(payload, sort_keys=True))
    raise SystemExit(2)

def require(condition, status, **extra):
    if not condition:
        fail(status, **extra)

def canonical_sha256(data):
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def validate(input_path, expected_path):
    data = json.loads(pathlib.Path(input_path).read_text(encoding="utf-8"))
    expected = json.loads(pathlib.Path(expected_path).read_text(encoding="utf-8"))

    require(expected.get("version") == 1, "OWNER_EXPECTED_SCHEMA_MISMATCH")
    require(
        expected.get("status") == "SIGNED_ARTIFACT_IDENTITY_FROZEN",
        "OWNER_SIGNED_ARTIFACT_IDENTITY_NOT_FROZEN",
        actual=expected.get("status"),
    )

    expected_hash = str(expected.get("artifact_sha256") or "").lower()
    expected_signer = str(expected.get("expected_signer_cert_sha256") or "").lower()
    require(HEX64.fullmatch(expected_hash) is not None, "OWNER_EXPECTED_APK_HASH_INVALID")
    require(HEX64.fullmatch(expected_signer) is not None, "OWNER_EXPECTED_SIGNER_HASH_INVALID")

    require(data.get("version") == 1, "OWNER_REAL_DEVICE_EVIDENCE_SCHEMA_MISMATCH")
    require(
        data.get("status") == "REAL_DEVICE_EVIDENCE_CAPTURED",
        "OWNER_REAL_DEVICE_CAPTURE_STATUS_INVALID",
        actual=data.get("status"),
    )
    require(
        data.get("git_head") == expected.get("target_head"),
        "OWNER_REAL_DEVICE_HEAD_MISMATCH",
        actual=data.get("git_head"),
        expected=expected.get("target_head"),
    )

    device = data.get("evidence") or {}
    runtime = data.get("phone_agent") or {}

    checks = {
        "package_name": (str(device.get("package_name", "")), expected.get("package_name")),
        "version_name": (str(device.get("version_name", "")), expected.get("version_name")),
        "version_code": (str(device.get("version_code", "")), str(expected.get("version_code"))),
        "artifact_sha256": (str(device.get("artifact_sha256", "")).lower(), expected_hash),
        "signer_cert_sha256": (str(device.get("signer_cert_sha256", "")).lower(), expected_signer),
    }
    mismatches = {k: {"actual": a, "expected": e} for k, (a, e) in checks.items() if a != e}
    require(not mismatches, "OWNER_REAL_DEVICE_IDENTITY_MISMATCH", mismatches=mismatches)

    for field in ("install_result", "launch_result", "postcondition_result"):
        require(
            device.get(field) == "PASS",
            "OWNER_REAL_DEVICE_POSTCONDITION_FAIL",
            field=field,
            actual=device.get(field),
        )

    require(
        runtime.get("implementation") == expected.get("runtime_implementation"),
        "OWNER_PHONE_AGENT_IMPLEMENTATION_MISMATCH",
        actual=runtime.get("implementation"),
        expected=expected.get("runtime_implementation"),
    )
    require(runtime.get("network_permission") == "NONE",
            "OWNER_PHONE_AGENT_NETWORK_POLICY_MISMATCH",
            actual=runtime.get("network_permission"))
    require(runtime.get("accessibility_enabled") is True,
            "OWNER_PHONE_AGENT_ACCESSIBILITY_NOT_ENABLED")
    require(runtime.get("service_connected") is True,
            "OWNER_PHONE_AGENT_SERVICE_NOT_CONNECTED")
    require(int(runtime.get("self_test_target_hits", 0)) > 0,
            "OWNER_PHONE_AGENT_SELF_TEST_TARGET_NOT_HIT",
            actual=runtime.get("self_test_target_hits"))
    require(runtime.get("runtime_postcondition_result") == "PASS",
            "OWNER_PHONE_AGENT_RUNTIME_POSTCONDITION_FAIL",
            actual=runtime.get("runtime_postcondition_result"))

    action_fields = {
        "TAP": "tap_pass",
        "CLICK_TEXT": "click_text_pass",
        "SCROLL_FORWARD": "scroll_forward_pass",
    }
    for action in expected.get("required_event_actions") or []:
        field = action_fields.get(action)
        require(field is not None, "OWNER_REQUIRED_ACTION_UNSUPPORTED", action=action)
        require(runtime.get(field) is True,
                "OWNER_PHONE_AGENT_ACTION_NOT_VERIFIED",
                action=action,
                field=field)

    events = runtime.get("events") or []
    passed = {
        e.get("action")
        for e in events
        if isinstance(e, dict) and e.get("status") == "PASS"
    }
    missing_events = [
        action for action in expected.get("required_event_actions") or []
        if action not in passed
    ]
    require(not missing_events,
            "OWNER_PHONE_AGENT_EVENT_EVIDENCE_INCOMPLETE",
            missing=missing_events)
    require(
        any(
            isinstance(e, dict)
            and e.get("action") == "SERVICE"
            and e.get("status") == "READY"
            for e in events
        ),
        "OWNER_PHONE_AGENT_SERVICE_READY_EVENT_MISSING",
    )

    return {
        "version": 1,
        "status": "OWNER_REAL_DEVICE_EVIDENCE_VERIFIED",
        "target_head": expected.get("target_head"),
        "package_name": expected.get("package_name"),
        "version_name": expected.get("version_name"),
        "version_code": expected.get("version_code"),
        "artifact_sha256": expected_hash,
        "signer_cert_sha256": expected_signer,
        "device_model": device.get("device_model"),
        "android_version": device.get("android_version"),
        "captured_at_epoch_ms": data.get("captured_at_epoch_ms"),
        "self_test_target_hits": runtime.get("self_test_target_hits"),
        "verified_actions": sorted(expected.get("required_event_actions") or []),
        "evidence_canonical_sha256": canonical_sha256(data),
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--expected", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    result = validate(args.input, args.expected)
    rendered = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output:
        out = pathlib.Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
    print(json.dumps(result, sort_keys=True))

if __name__ == "__main__":
    main()
