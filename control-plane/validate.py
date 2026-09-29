#!/usr/bin/env python3
import hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent
FILE_VERSIONS = {
    'security/baseline.json': {1},
    'evidence/pipeline.json': {1},
    'connectors/permissions.json': {1},
    'agents/boundary.json': {1},
    'models/router.json': {1},
    'runtime/security.json': {1},
    'runtime/device_schema.json': {1},
    'runtime/phone_agent.json': {2},
    'recovery/state.json': {1},
}

def fail(msg):
    print(f'CONTROL_PLANE_VALIDATION_FAIL: {msg}', file=sys.stderr)
    raise SystemExit(1)

records=[]
for rel, allowed_versions in FILE_VERSIONS.items():
    path=ROOT/rel
    if not path.is_file(): fail(f'missing {rel}')
    try: data=json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc: fail(f'invalid JSON {rel}: {exc}')
    if data.get('version') not in allowed_versions:
        fail(f'unsupported version in {rel}: {data.get("version")}')
    records.append({'file':rel,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'version':data.get('version')})

for rel in [
    'evidence/frozen_head.py',
    'connectors/authorize.py',
    'agents/enforce.py',
    'models/route.py',
    'models/runtime_smoke.py',
    'runtime/check_policy.py',
    'runtime/device_evidence.py',
    'runtime/phone_agent.py',
    'recovery/checkpoint.py'
]:
    if not (ROOT/rel).is_file(): fail(f'missing executable {rel}')

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
verified_execution=[p for p in router.get('providers',[]) if p.get('execution')=='VERIFIED']
if not verified_execution: fail('at least one model execution provider must be verified')
for provider in verified_execution:
    evidence=provider.get('evidence')
    if not isinstance(evidence,dict): fail(f'model provider missing evidence: {provider.get("name")}')
    for key in ('run_id','artifact_id','artifact_sha256','exact_head'):
        if not evidence.get(key): fail(f'model provider evidence incomplete: {provider.get("name")}:{key}')

runtime=json.loads((ROOT/'runtime/security.json').read_text())
constraints=runtime.get('constraints',{})
if not constraints.get('preserve_original_bytes'): fail('runtime must preserve original bytes')
for key in ('root','bootloader_unlock','repack','resign'):
    if constraints.get(key) is not False: fail(f'runtime constraint must remain disabled: {key}')
if 'real-device-install' not in set(runtime.get('user_gate',[])): fail('real device install must remain user gated')

schema=json.loads((ROOT/'runtime/device_schema.json').read_text())
needed={'device_model','android_version','package_name','version_name','version_code','artifact_sha256','install_result','launch_result','postcondition_result'}
if not needed.issubset(set(schema.get('required_fields',[]))): fail('device evidence schema incomplete')

phone=json.loads((ROOT/'runtime/phone_agent.json').read_text())
if phone.get('implementation')!='android-accessibility-local-explicit-user-control':
    fail('phone agent implementation marker mismatch')
if phone.get('network_permission') is not False: fail('phone agent must not require INTERNET permission')
actions=phone.get('actions',{})
required_action_states={
    'accessibility_enablement':'USER_GATE',
    'back':'ALLOW_AFTER_SERVICE_ENABLEMENT',
    'home':'ALLOW_AFTER_SERVICE_ENABLEMENT',
    'recents':'ALLOW_AFTER_SERVICE_ENABLEMENT',
    'tap':'ALLOW_AFTER_SERVICE_ENABLEMENT',
    'click_visible_text':'ALLOW_AFTER_SERVICE_ENABLEMENT',
    'scroll':'ALLOW_AFTER_SERVICE_ENABLEMENT',
    'install_on_real_device':'USER_GATE',
    'alter_baseline_artifact':'DENY',
    'export_credentials':'DENY',
    'root_device':'DENY',
    'unlock_bootloader':'DENY'
}
for action, expected in required_action_states.items():
    if actions.get(action)!=expected: fail(f'phone agent policy mismatch: {action}')

recovery=json.loads((ROOT/'recovery/state.json').read_text())
if recovery.get('rollback_strategy')!='branch-and-pr': fail('recovery must use branch-and-pr')
if recovery.get('external_archive')!='VERIFIED': fail('external evidence archive must be verified')
if not recovery.get('merge_requires_explicit_approval'): fail('recovery merge must require explicit approval')
required_sources={'git-head','ci-artifact-hash','drive-readback-hash'}
if not required_sources.issubset(set(recovery.get('required_sources',[]))): fail('recovery source set incomplete')

print(json.dumps({
    'status':'CONTROL_PLANE_VALIDATION_PASS',
    'files':records,
    'connectors':len(connectors['connectors']),
    'phone_agent_runtime':'android-accessibility-local-explicit-user-control',
    'verified_model_execution_providers':[p['name'] for p in verified_execution]
},sort_keys=True))
