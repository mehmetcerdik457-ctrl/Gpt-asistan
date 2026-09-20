#!/usr/bin/env python3
import hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent
FILES = [
    "security/baseline.json",
    "evidence/pipeline.json",
    "connectors/permissions.json",
    "agents/boundary.json",
    "models/router.json",
    "runtime/security.json",
    "recovery/state.json",
]

def fail(msg):
    print(f"CONTROL_PLANE_VALIDATION_FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)

records = []
for rel in FILES:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing {rel}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid JSON {rel}: {exc}")
    if data.get("version") != 1:
        fail(f"unsupported version in {rel}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    records.append({"file": rel, "sha256": digest})

security = json.loads((ROOT/"security/baseline.json").read_text())
if any(security[k] for k in ("production_source","production_credentials","production_deployment")):
    fail("production scope must remain disabled")
if not all(security[k] for k in ("require_pull_request","require_ci","require_evidence")):
    fail("hardening gates must stay enabled")

connectors = json.loads((ROOT/"connectors/permissions.json").read_text())
if connectors.get("default_access") != "deny":
    fail("connector default_access must be deny")
if not connectors.get("require_explicit_authorization"):
    fail("connector authorization gate missing")

agents = json.loads((ROOT/"agents/boundary.json").read_text())
required_denies={"production-deploy","production-secret-read","credential-export"}
if not required_denies.issubset(set(agents.get("deny", []))):
    fail("agent deny boundary incomplete")

out = {"status":"CONTROL_PLANE_VALIDATION_PASS","files":records}
print(json.dumps(out, sort_keys=True))
