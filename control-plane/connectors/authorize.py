#!/usr/bin/env python3
import argparse, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent
DATA = json.loads((ROOT / 'permissions.json').read_text(encoding='utf-8'))

def decision(name: str, capability: str):
    item = DATA['connectors'].get(name)
    if item is None:
        return {'connector': name, 'capability': capability, 'decision': 'DENY', 'reason': 'unknown-connector'}
    status = item.get(capability, 'NOT_VERIFIED')
    allowed = status.startswith('VERIFIED')
    if capability == 'write' and not item.get('project_write_authorized', False):
        allowed = False
    return {
        'connector': name,
        'capability': capability,
        'status': status,
        'decision': 'ALLOW' if allowed else 'DENY',
        'purpose': item.get('purpose'),
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument('connector')
    p.add_argument('capability', choices=['read','write','admin','owner'])
    p.add_argument('--expect', choices=['allow','deny'])
    args = p.parse_args()
    result = decision(args.connector, args.capability)
    print(json.dumps(result, sort_keys=True))
    if args.expect:
        expected = args.expect.upper()
        if result['decision'] != expected:
            raise SystemExit(2)

if __name__ == '__main__':
    main()
