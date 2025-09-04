from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
import os, json, time

r = APIRouter()
FILE = os.path.expanduser("~/.ga.memory.jsonl")

class MemItem(BaseModel):
    role: str = "system"
    content: str

def _load() -> List[dict]:
    items = []
    if os.path.exists(FILE):
        with open(FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    items.append(json.loads(line))
                except Exception:
                    pass
    return items

def _append(obj: dict):
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    with open(FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

@r.post("/memory/add")
def add(item: MemItem):
    _append({"role": item.role, "content": item.content, "ts": int(time.time())})
    return {"ok": True}

@r.post("/memory/clear")
def clear():
    try:
        os.remove(FILE)
    except FileNotFoundError:
        pass
    return {"ok": True}

@r.get("/memory/show")
def show():
    return {"ok": True, "items": _load()}

def build_system_prompt() -> str:
    notes = [it.get("content","") for it in _load() if it.get("role") == "system"]
    if not notes:
        return ""
    base = "Aşağıdaki kurallara harfiyen uy:\n"
    for n in notes:
        if n.strip():
            base += f"- {n.strip()}\n"
    return base


# --- minimal init for app startup ---
def init():
    return True
