"""CLI for status, doctor, list and bounded worker dispatch."""
import argparse, asyncio, json
from .registry import WORKERS,dispatch,fleet_status
from .doctor import diagnose
def main():
 p=argparse.ArgumentParser(); s=p.add_subparsers(dest="cmd",required=True)
 s.add_parser("status"); s.add_parser("doctor"); s.add_parser("list")
 r=s.add_parser("run"); r.add_argument("worker_ids",nargs="+"); r.add_argument("--concurrency",type=int,default=4)
 a=p.parse_args()
 if a.cmd=="status": out=fleet_status()
 elif a.cmd=="doctor": out=diagnose()
 elif a.cmd=="list": out=[w.__dict__ for w in WORKERS]
 else: out=asyncio.run(dispatch(a.worker_ids,a.concurrency))
 print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
