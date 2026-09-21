#!/usr/bin/env python3
import argparse, hashlib, json, pathlib

ROOT=pathlib.Path(__file__).resolve().parents[1]
FILES=[
 'security/baseline.json',
 'evidence/pipeline.json',
 'connectors/permissions.json',
 'agents/boundary.json',
 'models/router.json',
 'runtime/security.json',
 'runtime/device_schema.json',
 'runtime/phone_agent.json',
 'recovery/state.json'
]

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def create(head,output):
    data={'version':1,'head_sha':head,'status':'READY_FOR_REAL_DEVICE_EVIDENCE','files':{rel:sha(ROOT/rel) for rel in FILES}}
    pathlib.Path(output).write_text(json.dumps(data,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':data['status'],'head_sha':head,'files':len(FILES)},sort_keys=True))

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
