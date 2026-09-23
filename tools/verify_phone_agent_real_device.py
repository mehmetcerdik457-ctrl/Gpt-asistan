#!/usr/bin/env python3
import argparse, hashlib, json, pathlib, sys

def canonical_sha256(data):
    encoded=json.dumps(data,sort_keys=True,separators=(",",":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def fail(status, **extra):
    payload={"status":status, **extra}
    print(json.dumps(payload,sort_keys=True))
    raise SystemExit(2)

def require(condition, status, **extra):
    if not condition:
        fail(status, **extra)

def validate(input_path, expected_path):
    data=json.loads(pathlib.Path(input_path).read_text(encoding="utf-8"))
    expected=json.loads(pathlib.Path(expected_path).read_text(encoding="utf-8"))

    require(data.get("version")==3, "REAL_DEVICE_EVIDENCE_SCHEMA_MISMATCH", actual=data.get("version"), expected=3)
    require(data.get("status")=="REAL_DEVICE_EVIDENCE_CAPTURED", "REAL_DEVICE_CAPTURE_STATUS_INVALID", actual=data.get("status"))
    require(data.get("git_head")==expected["target_head"], "REAL_DEVICE_HEAD_MISMATCH", actual=data.get("git_head"), expected=expected["target_head"])

    device=data.get("evidence") or {}
    runtime=data.get("phone_agent") or {}

    checks={
        "package_name": (str(device.get("package_name","")), expected["package_name"]),
        "version_name": (str(device.get("version_name","")), expected["version_name"]),
        "version_code": (str(device.get("version_code","")), str(expected["version_code"])),
        "artifact_sha256": (str(device.get("artifact_sha256","")).lower(), expected["artifact_sha256"].lower()),
    }
    mismatches={k:{"actual":a,"expected":e} for k,(a,e) in checks.items() if a!=e}
    require(not mismatches, "REAL_DEVICE_IDENTITY_MISMATCH", mismatches=mismatches)

    for field in ("install_result","launch_result","postcondition_result"):
        require(device.get(field)=="PASS", "REAL_DEVICE_POSTCONDITION_FAIL", field=field, actual=device.get(field))

    require(runtime.get("implementation")==expected["runtime_implementation"],
            "PHONE_AGENT_IMPLEMENTATION_MISMATCH",
            actual=runtime.get("implementation"), expected=expected["runtime_implementation"])
    require(runtime.get("network_permission")=="NONE",
            "PHONE_AGENT_NETWORK_POLICY_MISMATCH", actual=runtime.get("network_permission"))
    require(runtime.get("accessibility_enabled") is True,
            "PHONE_AGENT_ACCESSIBILITY_NOT_ENABLED")
    require(runtime.get("service_connected") is True,
            "PHONE_AGENT_SERVICE_NOT_CONNECTED")
    require(int(runtime.get("self_test_target_hits",0)) > 0,
            "PHONE_AGENT_SELF_TEST_TARGET_NOT_HIT",
            actual=runtime.get("self_test_target_hits"))
    require(runtime.get("tap_pass") is True, "PHONE_AGENT_TAP_NOT_VERIFIED")
    require(runtime.get("click_text_pass") is True, "PHONE_AGENT_CLICK_TEXT_NOT_VERIFIED")
    require(runtime.get("scroll_forward_pass") is True, "PHONE_AGENT_SCROLL_NOT_VERIFIED")
    require(runtime.get("runtime_postcondition_result")=="PASS",
            "PHONE_AGENT_RUNTIME_POSTCONDITION_FAIL",
            actual=runtime.get("runtime_postcondition_result"))

    events=runtime.get("events") or []
    passed={e.get("action") for e in events if isinstance(e,dict) and e.get("status")=="PASS"}
    missing_events=[a for a in expected["required_event_actions"] if a not in passed]
    require(not missing_events, "PHONE_AGENT_EVENT_EVIDENCE_INCOMPLETE", missing=missing_events)

    require(any(isinstance(e,dict) and e.get("action")=="SERVICE" and e.get("status")=="READY" for e in events),
            "PHONE_AGENT_SERVICE_READY_EVENT_MISSING")

    return {
        "version":1,
        "status":"PHONE_AGENT_REAL_DEVICE_EVIDENCE_VERIFIED",
        "target_head":expected["target_head"],
        "package_name":expected["package_name"],
        "version_name":expected["version_name"],
        "version_code":expected["version_code"],
        "artifact_sha256":expected["artifact_sha256"],
        "device_model":device.get("device_model"),
        "android_version":device.get("android_version"),
        "captured_at_epoch_ms":data.get("captured_at_epoch_ms"),
        "self_test_target_hits":runtime.get("self_test_target_hits"),
        "verified_actions":sorted(expected["required_event_actions"]),
        "evidence_canonical_sha256":canonical_sha256(data),
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--expected",required=True)
    p.add_argument("--output")
    args=p.parse_args()
    result=validate(args.input,args.expected)
    rendered=json.dumps(result,sort_keys=True,indent=2)+"\n"
    if args.output:
        out=pathlib.Path(args.output)
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(rendered,encoding="utf-8")
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":
    main()
