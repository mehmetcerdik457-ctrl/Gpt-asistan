#!/usr/bin/env python3
import argparse, hashlib, json, pathlib

ROOT=pathlib.Path(__file__).resolve().parents[2]
FILES=[
 'control-plane/security/baseline.json',
 'control-plane/evidence/pipeline.json',
 'control-plane/connectors/permissions.json',
 'control-plane/agents/boundary.json',
 'control-plane/models/router.json',
 'control-plane/models/route.py',
 'control-plane/models/runtime_smoke.py',
 'control-plane/runtime/security.json',
 'control-plane/runtime/device_schema.json',
 'control-plane/runtime/device_evidence.py',
 'control-plane/runtime/phone_agent.json',
 'control-plane/runtime/phone_agent.py',
 'control-plane/recovery/state.json',
 '.github/workflows/control-plane-validation.yml',
 '.github/workflows/model-runtime.yml',
 '.github/workflows/android.yml',
 '.github/workflows/phone-agent-emulator.yml',
 'tools/phone_agent_emulator_verify.sh',
 'settings.gradle.kts',
 'build.gradle.kts',
 'app/build.gradle.kts',
 'app/src/main/AndroidManifest.xml',
 'app/src/main/java/com/example/gptasistan/MainActivity.kt',
 'app/src/main/java/com/example/gptasistan/PhoneActionPolicy.kt',
 'app/src/main/java/com/example/gptasistan/PhoneAgentAccessibilityService.kt',
 'app/src/main/java/com/mehmetcerdik/ownerai/BridgeClient.java',
 'app/src/main/java/com/mehmetcerdik/ownerai/OwnerControlPlaneActivity.java',
 'app/src/main/res/xml/accessibility_service_config.xml',
 'app/src/main/res/values/strings.xml',
 'app/src/main/res/values/themes.xml',
 'app/src/test/java/com/example/gptasistan/PhoneActionPolicyTest.kt'
]

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def create(head,output):
    files={rel:sha(ROOT/rel) for rel in FILES}
    data={'version':2,'head_sha':head,'status':'READY_FOR_PHONE_AGENT_REAL_DEVICE_EVIDENCE','files':files}
    pathlib.Path(output).write_text(json.dumps(data,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':data['status'],'head_sha':head,'files':len(files)},sort_keys=True))

def verify(manifest,expected_head):
    data=json.loads(pathlib.Path(manifest).read_text(encoding='utf-8'))
    if data.get('head_sha')!=expected_head: raise SystemExit('head mismatch')
    for rel,expected in data.get('files',{}).items():
        if sha(ROOT/rel)!=expected: raise SystemExit('file mismatch: '+rel)
    print(json.dumps({'status':'FROZEN_HEAD_MANIFEST_VERIFIED','head_sha':expected_head,'files':len(data.get('files',{}))},sort_keys=True))

def main():
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest='cmd',required=True)
    c=s.add_parser('create'); c.add_argument('--head-sha',required=True); c.add_argument('--output',required=True)
    v=s.add_parser('verify'); v.add_argument('--manifest',required=True); v.add_argument('--expected-head',required=True)
    a=p.parse_args()
    create(a.head_sha,a.output) if a.cmd=='create' else verify(a.manifest,a.expected_head)

if __name__=='__main__': main()
