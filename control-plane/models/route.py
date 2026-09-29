#!/usr/bin/env python3
import argparse, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / 'router.json').read_text(encoding='utf-8'))

def route(task_class: str, mode: str = 'execution', requested_provider: str | None = None):
    if mode not in {'discovery','execution'}:
        raise ValueError('invalid mode')
    providers = CONFIG.get('providers', [])
    if requested_provider:
        providers = [p for p in providers if p.get('name') == requested_provider]
    for provider in providers:
        if task_class not in provider.get('task_classes', []):
            continue
        if provider.get(mode) == 'VERIFIED':
            return {'decision':'ROUTE','provider':provider['name'],'mode':mode,'task_class':task_class}
    return {'decision':'DENY','provider':None,'mode':mode,'task_class':task_class,'reason':'no-verified-provider'}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('task_class')
    p.add_argument('--mode', choices=['discovery','execution'], default='execution')
    p.add_argument('--provider')
    p.add_argument('--expect', choices=['route','deny'])
    args=p.parse_args()
    result=route(args.task_class,args.mode,args.provider)
    print(json.dumps(result,sort_keys=True))
    if args.expect and result['decision'] != args.expect.upper():
        raise SystemExit(2)

if __name__ == '__main__':
    main()
