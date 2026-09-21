#!/usr/bin/env python3
import hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent
FILES = [
    'security/baseline.json',
    'evidence/pipeline.json',
    'connectors/permissions.json',
    'agents/boundary.json',
    'models/router.json',
    'runtime/security.json',
    'recovery/state.json',
]

def fail(msg):
    print(f'CONTROL_PLANE_VALIDATION_FAIL: {msg}', file=sys.stderr)
    raise SystemExit(1)

records=[]
for rel in FILES:
    path=ROOT/rel
    if not path.is_file(): fail(f'missing {rel}')
    try: data=json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc: fail(f'invalid JSON {rel}: {exc}')
    if data.get('version') != 1: fail(f'unsupported version in {rel}')
    records.append({'file':rel,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})

security=json.loads((ROOT/'security/baseline.json').read_text())
if any(security[k] for k in ('production_source','production_credentials','production_deployment')):
    fail('production scope must remain disabled')
if not all(security[k] for k in ('require_pull_request','require_ci','require_evidence')):
    fail('hardening gates must stay enabled')

connectors=json.loads((ROOT/'connectors/permissions.json').read_text())
if connectors.get('default_access') != 'deny': fail('connector default_access must be deny')
if not connectors.get('require_explicit_authorization'): fail('connector authorization gate missing')
required={'github','google_drive','gmail','outlook','notion','clickup','slack','hugging_face','replit','openai_platform'}
if not required.issubset(connectors.get('connectors',{})): fail('connector registry incomplete')
for name,item in connectors['connectors'].items():
    if item.get('write') == 'VERIFIED' and not item.get('project_write_authorized',False):
        fail(f'verified write without project authorization: {name}')

agents=json.loads((ROOT/'agents/boundary.json').read_text())
required_denies={'production-deploy','production-secret-read','credential-export','disable-security-controls'}
if not required_denies.issubset(set(agents.get('deny',[]))): fail('agent deny boundary incomplete')
if 'merge-main' not in set(agents.get('user_gate',[])): fail('merge-main must remain user gated')

router=json.loads((ROOT/'models/router.json').read_text())
if router.get('fallback') != 'none': fail('model router fallback must remain none')
if not router.get('require_provider_authorization'): fail('model router provider authorization gate missing')

print(json.dumps({'status':'CONTROL_PLANE_VALIDATION_PASS','files':records,'connectors':len(connectors['connectors'])},sort_keys=True))
