from typing import List, Dict, Any, Optional
import subprocess, shlex, os, tempfile

LLAMA_BIN = os.path.expanduser("~/llama.cpp/build/bin/llama-cli")
MODEL = "/sdcard/models/local.gguf"

def _hist_to_prompt(history: List[Dict[str, Any]]) -> str:
    parts=[]
    for m in history:
        role=m.get("role","user")
        if role not in ("user","assistant"):  # system vb. filtrele
            continue
        content=m.get("content","")
        parts.append(f"{role}: {content}")
    parts.append("assistant:")
    return "\n".join(parts)

def _run_llama(prompt: str) -> str:
    if not os.path.exists(LLAMA_BIN):
        return "Yerel LLM yok: ~/llama.cpp/build/bin/llama-cli bulunamadı."
    if not os.path.exists(MODEL):
        return "Yerel LLM yok: /sdcard/models/local.gguf ekle."
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        f.write(prompt); pfile=f.name
    # Yalnızca yeni user satırında dur; assistant’ta DURMA
    cmd = f'{shlex.quote(LLAMA_BIN)} -m {shlex.quote(MODEL)} -f {shlex.quote(pfile)} -n 128 -c 1024 --temp 0.8 --repeat-penalty 1.05 -r "\\nuser:"'
    try:
        out = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=180)
        txt = (out.stdout or out.stderr or "").strip()
        return txt if txt else "Yanıt üretilemedi."
    finally:
        try: os.unlink(pfile)
        except Exception: pass

def offline_reply(history: List[Dict[str, Any]]) -> str:
    return _run_llama(_hist_to_prompt(history))

async def call_openai(history: List[Dict[str, Any]]) -> Optional[str]:
    return None
