#!/usr/bin/env python3
import argparse, json, pathlib, re

ROOT=pathlib.Path(__file__).resolve().parent
SCHEMA=json.loads((ROOT/'device_schema.json').read_text(encoding='utf-8'))

def make_template(path):
    evidence={key:'' for key in SCHEMA['required_fields']}
    data={'version':1,'status':SCHEMA['status_without_device'],'git_head':'','evidence':evidence}
    pathlib.Path(path).write_text(json.dumps(data,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'DEVICE_EVIDENCE_TEMPLATE_CREATED','required':len(evidence)},sort_keys=True))

def validate(path, expected_path=None):
    data=json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
    evidence=data.get('evidence',{})
    missing=[k for k in SCHEMA['required_fields'] if evidence.get(k) in ('',None)]
    sha=str(evidence.get('artifact_sha256',''))
    if sha and not re.fullmatch(r'[0-9a-fA-F]{64}',sha): missing.append('artifact_sha256_format')
    for field,allowed in [('install_result',SCHEMA['install_results']),('launch_result',SCHEMA['launch_results']),('postcondition_result',SCHEMA['postcondition_results'])]:
        value=evidence.get(field)
        if value not in ('',None) and value not in allowed: missing.append(field+'_value')
    if missing:
        print(json.dumps({'status':'USER_GATE','missing':sorted(set(missing))},sort_keys=True))
        raise SystemExit(3)
    if not all(evidence[x]=='PASS' for x in ('install_result','launch_result','postcondition_result')):
        print(json.dumps({'status':'REAL_DEVICE_EVIDENCE_FAIL'},sort_keys=True))
        raise SystemExit(2)
    if expected_path:
        expected=json.loads(pathlib.Path(expected_path).read_text(encoding='utf-8'))
        checks={
            'git_head': (data.get('git_head'), expected.get('git_head')),
            'package_name': (evidence.get('package_name'), expected.get('package_name')),
            'version_name': (evidence.get('version_name'), expected.get('version_name')),
            'version_code': (str(evidence.get('version_code')), str(expected.get('version_code'))),
            'artifact_sha256': (str(evidence.get('artifact_sha256')).lower(), str(expected.get('artifact_sha256')).lower()),
        }
        mismatches={k:{'actual':a,'expected':e} for k,(a,e) in checks.items() if a!=e}
        if mismatches:
            print(json.dumps({'status':'REAL_DEVICE_EVIDENCE_MISMATCH','mismatches':mismatches},sort_keys=True))
            raise SystemExit(4)
    print(json.dumps({'status':'REAL_DEVICE_EVIDENCE_VALID','package_name':evidence['package_name'],'git_head':data.get('git_head')},sort_keys=True))

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('template'); a.add_argument('--output',required=True)
    b=sub.add_parser('validate'); b.add_argument('--input',required=True); b.add_argument('--expected')
    args=p.parse_args()
    make_template(args.output) if args.cmd=='template' else validate(args.input,args.expected)

if __name__=='__main__': main()
