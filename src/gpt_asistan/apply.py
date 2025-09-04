from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import subprocess, shlex

r = APIRouter()

class ApplyReq(BaseModel):
    code: str   # ör: "echo Merhaba Termux && uname -a"

def run(cmd: str):
    # bash -lc ile ardışık/pipe'lı komutları destekle
    p = subprocess.run(["/data/data/com.termux/files/usr/bin/bash","-lc", cmd],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.returncode, p.stdout

@r.post("/apply")
def apply(a: ApplyReq):
    code = (a.code or "").strip()
    if not code:
        raise HTTPException(400, "empty code")
    rc, out = run(code)
    return {"ok": rc == 0, "exit_code": rc, "out": out}
