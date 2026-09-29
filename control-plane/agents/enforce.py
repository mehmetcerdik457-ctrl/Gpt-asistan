#!/usr/bin/env python3
import argparse, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
POLICY = json.loads((ROOT / 'boundary.json').read_text(encoding='utf-8'))

def decide(action: str, user_approved: bool = False):
    if action in POLICY.get('deny', []):
        return {'action': action, 'decision': 'DENY', 'reason': 'hard-deny'}
    if action in POLICY.get('user_gate', []):
        return {'action': action, 'decision': 'ALLOW' if user_approved else 'USER_GATE', 'reason': 'explicit-user-approval-required'}
    if action in POLICY.get('allow_platform', []):
        return {'action': action, 'decision': 'ALLOW', 'reason': 'platform-allowlist'}
    return {'action': action, 'decision': 'DENY', 'reason': 'default-deny'}

def main():
    p = argparse.ArgumentParser()
    p.add_argument('action')
    p.add_argument('--user-approved', action='store_true')
    p.add_argument('--expect', choices=['allow','deny','user_gate'])
    args = p.parse_args()
    result = decide(args.action, args.user_approved)
    print(json.dumps(result, sort_keys=True))
    if args.expect and result['decision'] != args.expect.upper():
        raise SystemExit(2)

if __name__ == '__main__':
    main()
