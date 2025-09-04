from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import subprocess, shlex, pathlib, time

r = APIRouter()

def sh(cmd: str):
    return subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

class ActReq(BaseModel):
    kind: str      # call | sms | wa | site | backup
    number: Optional[str]=None
    message: Optional[str]=None

@r.post("/act")
def act(a: ActReq):
    k=a.kind.lower()
    if k not in {"call","sms","wa","site","backup"}:
        raise HTTPException(400,"unknown kind")

    if k=="call":
        if not a.number: raise HTTPException(400,"number required")
        out=sh(f"termux-telephony-call {shlex.quote(a.number)}")
        return {"ok":True,"detail":"calling","out":out.stdout}

    if k=="sms":
        if not a.number or not a.message: raise HTTPException(400,"number and message required")
        out=sh(f"termux-sms-send -n {shlex.quote(a.number)} {shlex.quote(a.message)}")
        return {"ok":True,"detail":"sms sent","out":out.stdout}

    if k=="wa":
        if not a.number or not a.message: raise HTTPException(400,"number and message required")
        import urllib.parse as U
        url=f"https://wa.me/{a.number}?text="+U.quote(a.message)
        sh(f"am start -a android.intent.action.VIEW -d {shlex.quote(url)} >/dev/null 2>&1 || termux-open-url {shlex.quote(url)}")
        return {"ok":True,"detail":"whatsapp opened"}

    if k=="site":
        d=pathlib.Path.home()/ "site"; d.mkdir(exist_ok=True)
        idx=d/"index.html"
        if not idx.exists():
            idx.write_text("<!doctype html><meta charset='utf-8'><title>Benim Site</title><h1>Merhaba</h1>",encoding="utf-8")
        ps=sh("ps -o pid,args | grep 'http.server 8088' | grep -v grep").stdout.strip()
        if not ps:
            sh(f"cd {shlex.quote(str(d))} && nohup python -m http.server 8088 >/dev/null 2>&1 &")
        ip=sh("ip -o -4 addr show wlan0 | awk '{print $4}' | cut -d/ -f1").stdout.strip() or "127.0.0.1"
        return {"ok":True,"url":f"http://{ip}:8088/"}

    bdir=pathlib.Path.home()/ "ga_backups"; bdir.mkdir(exist_ok=True)
    t=bdir/f"ga-{int(time.time())}.tar.gz"
    sh(f"tar czf {shlex.quote(str(t))} -C $HOME repos/gpt-asistan ga.log .ga.env 2>/dev/null || true")
    return {"ok":True,"file":str(t)}
