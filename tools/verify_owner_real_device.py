#!/usr/bin/env python3
"""Validate exported assertions; physical origin requires independent evidence.

These APK exporters do not attest device origin, a shared session, audit-chain
integrity, or an independently observed UI postcondition. Matching their JSON
must never promote a fixture or self-report to a real-device acceptance result.
"""
import argparse, copy, hashlib, json, pathlib, re, subprocess

OWNER_HEAD="c8b52661921f82d9e832a0dcf7eed514e970bf49"
OWNER_PACKAGE="com.mehmetcerdik.ownerai"
OWNER_VERSION_NAME="1.2.0"
OWNER_VERSION_CODE="4"
OWNER_UNSIGNED_SHA256="1b111730ca0649c36d289d2312ced71a160f7a51a4666def66f62f2d5fae0c9a"
OWNER_SIGNED_SHA256="be15d47df7573fe4da7500cbd31f5caf21df380f0084c623d6e7a4a5e15f84b7"
GEN2_SIGNER="279084a36b7c17a1663bfba5fe1c5bdac974f8ef4ce56b21000d882493e39448"
BRIDGE_SOURCE_HEAD="a2ed5974efc94b3bc7ed8d8cfcb6169330678f0d"
BRIDGE_PACKAGE="com.mehmetcerdik.ownerbridge"
BRIDGE_VERSION_NAME="1.1.0"
BRIDGE_VERSION_CODE="2"
BRIDGE_SIGNED_SHA256="8588f221bd91baf9b8a6183267dd9180ab019a94264b6dfb0d112279802d48f2"
HEX40=re.compile(r"^[0-9a-f]{40}$")
HEX64=re.compile(r"^[0-9a-f]{64}$")
CONTENT_STATUS="FULL_EVIDENCE_CONTENT_VALIDATED"
MAX_EVIDENCE_BYTES=4*1024*1024

def canonical_sha256(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def fail(status,**extra):
    print(json.dumps({"status":status,**extra},sort_keys=True)); raise SystemExit(2)

def require(cond,status,**extra):
    if not cond: fail(status,**extra)

def object_required(value,status):
    require(isinstance(value,dict),status)
    return value

def load_evidence(path):
    def reject_constant(_):
        raise ValueError("nonfinite")
    def unique_keys(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise ValueError("duplicate key")
            result[key]=value
        return result
    try:
        with pathlib.Path(path).open("rb") as stream:
            raw=stream.read(MAX_EVIDENCE_BYTES+1)
        require(len(raw)<=MAX_EVIDENCE_BYTES,"EVIDENCE_TOO_LARGE")
        value=json.loads(raw.decode("utf-8"),object_pairs_hook=unique_keys,parse_constant=reject_constant)
    except (OSError,UnicodeError,ValueError,RecursionError):
        fail("EVIDENCE_INPUT_INVALID")
    return object_required(value,"EVIDENCE_OBJECT_REQUIRED")

def verify_checkout_head(expected):
    require(isinstance(expected,str) and HEX40.fullmatch(expected)!=None,"VERIFIER_HEAD_INVALID")
    try:
        actual=subprocess.run(["git","-C",str(pathlib.Path(__file__).resolve().parents[1]),
                               "rev-parse","HEAD"],check=True,capture_output=True,text=True).stdout.strip()
    except (OSError,subprocess.CalledProcessError):
        fail("VERIFIER_CHECKOUT_UNAVAILABLE")
    require(actual==expected,"VERIFIER_CHECKOUT_MISMATCH")
    try:
        committed=subprocess.run(["git","-C",str(pathlib.Path(__file__).resolve().parents[1]),
                                   "show","HEAD:tools/verify_owner_real_device.py"],
                                  check=True,capture_output=True,text=True).stdout
        require(committed==pathlib.Path(__file__).read_text(encoding="utf-8"),"VERIFIER_SOURCE_MISMATCH")
    except (OSError,UnicodeError,subprocess.CalledProcessError):
        fail("VERIFIER_SOURCE_UNAVAILABLE")
    return actual

def contract(verifier_head=None):
    if verifier_head is not None:
        require(isinstance(verifier_head,str) and HEX40.fullmatch(verifier_head)!=None,"VERIFIER_HEAD_INVALID")
    return {
      "version":3,
      "validation_scope":"EXPORTED_ASSERTIONS_ONLY",
      "physical_device_status":"NOT_VERIFIED",
      "success_status":CONTENT_STATUS,
      "verifier_head":verifier_head,
      "owner":{"source_head":OWNER_HEAD,"package":OWNER_PACKAGE,"version_name":OWNER_VERSION_NAME,
        "version_code":OWNER_VERSION_CODE,"unsigned_sha256":OWNER_UNSIGNED_SHA256,
        "signed_sha256":OWNER_SIGNED_SHA256,"signer_sha256":GEN2_SIGNER},
      "bridge":{"source_head":BRIDGE_SOURCE_HEAD,"package":BRIDGE_PACKAGE,"version_name":BRIDGE_VERSION_NAME,
        "version_code":BRIDGE_VERSION_CODE,"signed_sha256":BRIDGE_SIGNED_SHA256,
        "signer_sha256":GEN2_SIGNER,"network_permission":"NONE"},
      "required_actions":["OPEN","TAP","SWIPE","TYPE","VERIFY","RECORD"]
    }

def validate_owner(data):
    object_required(data,"OWNER_OBJECT_REQUIRED")
    require(type(data.get("version")) is int and data["version"]==3,"OWNER_SCHEMA_MISMATCH")
    require(data.get("status")=="REAL_DEVICE_EVIDENCE_CAPTURED","OWNER_CAPTURE_STATUS_INVALID",actual=data.get("status"))
    require(data.get("git_head")==OWNER_HEAD,"OWNER_HEAD_MISMATCH",actual=data.get("git_head"),expected=OWNER_HEAD)
    d=object_required(data.get("evidence"),"OWNER_EVIDENCE_OBJECT_REQUIRED")
    r=object_required(data.get("phone_agent"),"OWNER_RUNTIME_OBJECT_REQUIRED")
    for field in ("device_model","android_version"):
        require(isinstance(d.get(field),str) and bool(d[field].strip()),"OWNER_DEVICE_METADATA_MISSING",field=field)
    checks={
      "package_name":(str(d.get("package_name","")),OWNER_PACKAGE),
      "version_name":(str(d.get("version_name","")),OWNER_VERSION_NAME),
      "version_code":(str(d.get("version_code","")),OWNER_VERSION_CODE),
      "artifact_sha256":(str(d.get("artifact_sha256","")).lower(),OWNER_SIGNED_SHA256),
      "signer_cert_sha256":(str(d.get("signer_cert_sha256","")).lower(),GEN2_SIGNER)
    }
    mm={k:{"actual":a,"expected":e} for k,(a,e) in checks.items() if a!=e}
    require(not mm,"OWNER_IDENTITY_MISMATCH",mismatches=mm)
    for field in ("install_result","launch_result","postcondition_result"):
        require(d.get(field)=="PASS","OWNER_POSTCONDITION_FAIL",field=field,actual=d.get(field))
    require(r.get("implementation")=="v1_accessibility","OWNER_RUNTIME_IMPLEMENTATION_MISMATCH")
    require(r.get("network_permission")=="NONE","OWNER_NETWORK_POLICY_MISMATCH")
    require(r.get("accessibility_enabled") is True,"OWNER_ACCESSIBILITY_NOT_ENABLED")
    require(r.get("service_connected") is True,"OWNER_SERVICE_NOT_CONNECTED")
    hits=r.get("self_test_target_hits")
    require(type(hits) is int and hits>0,"OWNER_SELF_TEST_TARGET_NOT_HIT")
    for field,status in (("tap_pass","OWNER_TAP_NOT_VERIFIED"),("click_text_pass","OWNER_CLICK_TEXT_NOT_VERIFIED"),("scroll_forward_pass","OWNER_SCROLL_NOT_VERIFIED")):
        require(r.get(field) is True,status)
    require(r.get("runtime_postcondition_result")=="PASS","OWNER_RUNTIME_POSTCONDITION_FAIL")
    events=r.get("events")
    require(isinstance(events,list) and all(isinstance(e,dict) for e in events),"OWNER_EVENTS_INVALID")
    require(all(isinstance(e.get("action"),str) and isinstance(e.get("status"),str) for e in events),"OWNER_EVENTS_INVALID")
    passed={e.get("action") for e in events if isinstance(e,dict) and e.get("status")=="PASS"}
    require({"TAP","CLICK_TEXT","SCROLL_FORWARD"}.issubset(passed),"OWNER_EVENT_EVIDENCE_INCOMPLETE",passed=sorted(passed))
    require(any(isinstance(e,dict) and e.get("action")=="SERVICE" and e.get("status")=="READY" for e in events),"OWNER_SERVICE_READY_EVENT_MISSING")
    return {"device_model":d.get("device_model"),"android_version":d.get("android_version"),"hash":canonical_sha256(data)}

def validate_bridge(data):
    object_required(data,"BRIDGE_OBJECT_REQUIRED")
    require(type(data.get("version")) is int and data["version"]==1,"BRIDGE_SCHEMA_MISMATCH")
    require(data.get("status")=="BRIDGE_FINAL_EVIDENCE_CAPTURED","BRIDGE_CAPTURE_STATUS_INVALID",actual=data.get("status"))
    checks={
      "bridge_package":(str(data.get("bridge_package","")),BRIDGE_PACKAGE),
      "bridge_version_name":(str(data.get("bridge_version_name","")),BRIDGE_VERSION_NAME),
      "bridge_version_code":(str(data.get("bridge_version_code","")),BRIDGE_VERSION_CODE),
      "bridge_artifact_sha256":(str(data.get("bridge_artifact_sha256","")).lower(),BRIDGE_SIGNED_SHA256),
      "bridge_signer_cert_sha256":(str(data.get("bridge_signer_cert_sha256","")).lower(),GEN2_SIGNER),
      "owner_package":(str(data.get("owner_package","")),OWNER_PACKAGE),
      "owner_signer_cert_sha256":(str(data.get("owner_signer_cert_sha256","")).lower(),GEN2_SIGNER),
      "network_permission":(str(data.get("network_permission","")),"NONE")
    }
    mm={k:{"actual":a,"expected":e} for k,(a,e) in checks.items() if a!=e}
    require(not mm,"BRIDGE_IDENTITY_OR_POLICY_MISMATCH",mismatches=mm)
    require(data.get("service_connected") is True,"BRIDGE_SERVICE_NOT_CONNECTED")
    require(data.get("launch_app_pass") is True,"BRIDGE_OPEN_LAUNCH_NOT_VERIFIED")
    require(data.get("swipe_pass") is True,"BRIDGE_SWIPE_NOT_VERIFIED")
    require(data.get("type_text_pass") is True,"BRIDGE_TYPE_NOT_VERIFIED")
    require(data.get("verify_postcondition_pass") is True,"BRIDGE_VERIFY_POSTCONDITION_NOT_VERIFIED")
    events=data.get("events")
    require(isinstance(events,list) and all(isinstance(e,dict) for e in events),"BRIDGE_EVENTS_INVALID")
    require(all(isinstance(e.get("action"),str) and isinstance(e.get("status"),str) for e in events),"BRIDGE_EVENTS_INVALID")
    passed={e.get("action") for e in events if isinstance(e,dict) and e.get("status")=="PASS"}
    require({"LAUNCH_APP","SWIPE","TYPE_TEXT"}.issubset(passed),"BRIDGE_EVENT_EVIDENCE_INCOMPLETE",passed=sorted(passed))
    require(any(isinstance(e,dict) and e.get("action")=="SERVICE" and e.get("status")=="READY" for e in events),"BRIDGE_SERVICE_READY_EVENT_MISSING")
    return {"hash":canonical_sha256(data)}

def validate_full(owner,bridge,verifier_head):
    require(isinstance(verifier_head,str) and HEX40.fullmatch(verifier_head)!=None,"VERIFIER_HEAD_INVALID",actual=verifier_head)
    o=validate_owner(owner); b=validate_bridge(bridge)
    return {
      "version":3,"status":CONTENT_STATUS,"verifier_head":verifier_head,
      "verifier_head_binding":"CALLER_SUPPLIED_UNLESS_CLI_CHECKOUT_VERIFIED",
      "validation_scope":"EXPORTED_ASSERTIONS_ONLY","physical_device_status":"NOT_VERIFIED",
      "unverified_requirements":["physical_device_origin","same_device_and_fresh_session",
        "independent_screen_postcondition","audit_chain_integrity","durable_record_readback"],
      "owner_source_head":OWNER_HEAD,"owner_apk_sha256":OWNER_SIGNED_SHA256,"owner_signer_sha256":GEN2_SIGNER,
      "bridge_source_head":BRIDGE_SOURCE_HEAD,"bridge_apk_sha256":BRIDGE_SIGNED_SHA256,"bridge_signer_sha256":GEN2_SIGNER,
      "reported_actions":["OPEN","TAP","SWIPE","TYPE","VERIFY"],
      "device_model":o["device_model"],"android_version":o["android_version"],
      "owner_evidence_sha256":o["hash"],"bridge_evidence_sha256":b["hash"]
    }

def owner_fixture():
    return {"version":3,"status":"REAL_DEVICE_EVIDENCE_CAPTURED","git_head":OWNER_HEAD,"captured_at_epoch_ms":1,
      "evidence":{"device_model":"CI","android_version":"15","package_name":OWNER_PACKAGE,"version_name":OWNER_VERSION_NAME,
        "version_code":OWNER_VERSION_CODE,"artifact_sha256":OWNER_SIGNED_SHA256,"signer_cert_sha256":GEN2_SIGNER,
        "install_result":"PASS","launch_result":"PASS","postcondition_result":"PASS"},
      "phone_agent":{"implementation":"v1_accessibility","accessibility_enabled":True,"service_connected":True,"network_permission":"NONE",
        "self_test_target_hits":1,"tap_pass":True,"click_text_pass":True,"scroll_forward_pass":True,"runtime_postcondition_result":"PASS",
        "events":[{"action":"SERVICE","status":"READY"},{"action":"TAP","status":"PASS"},{"action":"CLICK_TEXT","status":"PASS"},{"action":"SCROLL_FORWARD","status":"PASS"}]}}
def bridge_fixture():
    return {"version":1,"status":"BRIDGE_FINAL_EVIDENCE_CAPTURED","bridge_package":BRIDGE_PACKAGE,
      "bridge_version_name":BRIDGE_VERSION_NAME,"bridge_version_code":BRIDGE_VERSION_CODE,
      "bridge_artifact_sha256":BRIDGE_SIGNED_SHA256,"bridge_signer_cert_sha256":GEN2_SIGNER,
      "owner_package":OWNER_PACKAGE,"owner_signer_cert_sha256":GEN2_SIGNER,"network_permission":"NONE",
      "service_connected":True,"launch_app_pass":True,"swipe_pass":True,"type_text_pass":True,"verify_postcondition_pass":True,
      "events":[{"action":"SERVICE","status":"READY"},{"action":"LAUNCH_APP","status":"PASS"},{"action":"SWIPE","status":"PASS"},{"action":"TYPE_TEXT","status":"PASS"}]}

def self_test(verifier_head):
    good=validate_full(owner_fixture(),bridge_fixture(),verifier_head)
    assert good["status"]==CONTENT_STATUS
    assert good["physical_device_status"]=="NOT_VERIFIED"
    negatives=[]
    x=copy.deepcopy(owner_fixture());x["evidence"]["artifact_sha256"]="0"*64;negatives.append((x,bridge_fixture()))
    x=copy.deepcopy(bridge_fixture());x["bridge_artifact_sha256"]="0"*64;negatives.append((owner_fixture(),x))
    x=copy.deepcopy(bridge_fixture());x["bridge_signer_cert_sha256"]="0"*64;negatives.append((owner_fixture(),x))
    x=copy.deepcopy(bridge_fixture());x["swipe_pass"]=False;negatives.append((owner_fixture(),x))
    x=copy.deepcopy(bridge_fixture());x["type_text_pass"]=False;negatives.append((owner_fixture(),x))
    for o,b in negatives:
        try: validate_full(o,b,verifier_head)
        except SystemExit: pass
        else: raise AssertionError("negative fixture unexpectedly accepted")
    print(json.dumps({"status":"FULL_EVIDENCE_VERIFIER_SELF_TEST_PASS","physical_device_status":"NOT_VERIFIED","verifier_head":verifier_head},sort_keys=True))

def main():
    p=argparse.ArgumentParser();p.add_argument("--owner-input");p.add_argument("--bridge-input");p.add_argument("--output")
    p.add_argument("--verifier-head");p.add_argument("--self-test",action="store_true");p.add_argument("--print-contract",action="store_true")
    a=p.parse_args()
    if a.self_test: self_test(a.verifier_head or "0"*40);return
    if a.print_contract: print(json.dumps(contract(a.verifier_head),sort_keys=True,indent=2));return
    if not a.owner_input or not a.bridge_input or not a.verifier_head: p.error("--owner-input, --bridge-input and --verifier-head are required")
    actual=verify_checkout_head(a.verifier_head)
    owner=load_evidence(a.owner_input);bridge=load_evidence(a.bridge_input)
    result=validate_full(owner,bridge,actual)
    result["verifier_head_binding"]="EXACT_CHECKOUT_VERIFIED"
    result["verifier_source_sha256"]=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
    render=json.dumps(result,sort_keys=True,indent=2)+"\n"
    if a.output:
        out=pathlib.Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(render)
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__": main()
