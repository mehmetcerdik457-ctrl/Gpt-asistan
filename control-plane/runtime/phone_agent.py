#!/usr/bin/env python3
import json, pathlib, sys

ROOT=pathlib.Path(__file__).resolve().parent
POLICY=json.loads((ROOT/'phone_agent.json').read_text(encoding='utf-8'))
action=sys.argv[1] if len(sys.argv)>1 else ''
decision=POLICY.get('actions',{}).get(action,'DENY')
print(json.dumps({'action':action,'decision':decision},sort_keys=True))
if len(sys.argv)>2:
    expected=sys.argv[2].upper()
    if decision!=expected: raise SystemExit(2)
