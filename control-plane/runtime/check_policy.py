#!/usr/bin/env python3
import json, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parent
P=json.loads((ROOT/'security.json').read_text())
op=sys.argv[1] if len(sys.argv)>1 else ''
if op in P.get('allow',[]): decision='ALLOW'
elif op in P.get('user_gate',[]): decision='USER_GATE'
else: decision='DENY'
print(json.dumps({'operation':op,'decision':decision},sort_keys=True))
