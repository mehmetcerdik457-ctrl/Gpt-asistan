#!/usr/bin/env python3
import argparse, hashlib, json, pathlib

ROOT=pathlib.Path(__file__).resolve().parents[1]
CRITICAL=[
 'security/baseline.json',
 'evidence/pipeline.json',
 'evidence/frozen_head.py',
 'connectors/permissions.json',
 'connectors/authorize.py',
 'agents/boundary.json',
 'agents/enforce.py',
 'models/router.json',
 'models/route.py',
 'models/runtime_smoke.py',
 'runtime/security.json',
 'runtime/check_policy.py',
 'runtime/device_schema.json',
 'runtime/device_evidence.py',
 'runtime/phone_agent.json',
 'runtime/phone_agent.py',
 'recovery/state.json'
]

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def create(head_sha, output):
    files={rel:digest(ROOT/rel) for rel in CRITICAL}
    data={'version':1,'head_sha':head_sha,'restore_strategy':'branch-and-pr','files':files}
    pathlib.Path(output).write_text(json.dumps(data,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'RECOVERY_CHECKPOINT_CREATED','head_sha':head_sha,'files':len(files)},sort_keys=True))

def verify(manifest):
    data=json.loads(pathlib.Path(manifest).read_text(encoding='utf-8'))
    if data.get('restore_strategy')!='branch-and-pr': raise SystemExit('invalid restore strategy')
    for rel,expected in data.get('files',{}).items():
        if digest(ROOT/rel)!=expected: raise SystemExit('hash mismatch: '+rel)
    print(json.dumps({'status':'RECOVERY_CHECKPOINT_VERIFIED','head_sha':data.get('head_sha'),'files':len(data.get('files',{}))},sort_keys=True))

def main():
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest='cmd',required=True)
    c=s.add_parser('create'); c.add_argument('--head-sha',required=True); c.add_argument('--output',required=True)
    v=s.add_parser('verify'); v.add_argument('--manifest',required=True)
    a=p.parse_args()
    create(a.head_sha,a.output) if a.cmd=='create' else verify(a.manifest)

if __name__=='__main__': main()
