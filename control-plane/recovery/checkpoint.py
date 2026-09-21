#!/usr/bin/env python3
import argparse, hashlib, json, pathlib, sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
CRITICAL=[
 'security/baseline.json',
 'evidence/pipeline.json',
 'connectors/permissions.json',
 'agents/boundary.json',
 'models/router.json',
 'runtime/security.json',
 'recovery/state.json'
]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def create(head_sha, output):
    files={rel:digest(ROOT/rel) for rel in CRITICAL}
    data={'version':1,'head_sha':head_sha,'restore_strategy':'branch-and-pr','files':files}
    pathlib.Path(output).write_text(json.dumps(data,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'RECOVERY_CHECKPOINT_CREATED','head_sha':head_sha,'files':len(files)},sort_keys=True))

def verify(manifest):
    data=json.loads(pathlib.Path(manifest).read_text(encoding='utf-8'))
    if data.get('restore_strategy')!='branch-and-pr': raise SystemExit('invalid restore strategy')
    for rel,expected in data.get('files',{}).items():
        actual=digest(ROOT/rel)
        if actual!=expected: raise SystemExit(f'hash mismatch: {rel}')
    print(json.dumps({'status':'RECOVERY_CHECKPOINT_VERIFIED','head_sha':data.get('head_sha'),'files':len(data.get('files',{}))},sort_keys=True))

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True)
    c=sub.add_parser('create'); c.add_argument('--head-sha',required=True); c.add_argument('--output',required=True)
    v=sub.add_parser('verify'); v.add_argument('--manifest',required=True)
    a=p.parse_args()
    if a.cmd=='create': create(a.head_sha,a.output)
    else: verify(a.manifest)

if __name__=='__main__': main()
