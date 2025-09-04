from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from . import memory
from .provider import call_openai, offline_reply
from .openai_compat import r as openai_router
from .apply import r as apply_router
from .memory import r as memory_router
from .actions import r as actions_router

app = FastAPI(title="GPT Asistan (Hafif)")
app.include_router(openai_router)
app.include_router(apply_router)
app.include_router(memory_router)
app.include_router(actions_router)

class Msg(BaseModel):
    session: str = "default"
    content: str

@app.on_event("startup")
def _startup():
    memory.init()

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/chat")
async def chat(m: Msg):
    txt = m.content.strip()
    memory.add(m.session, "user", txt)
    hist = memory.history(m.session, 30)
    ai = await call_openai(hist) or offline_reply(hist)
    memory.add(m.session, "assistant", ai)
    return {"reply": ai, "session": m.session}


@app.get('/ui', response_class=HTMLResponse)
def ui():
    p = Path(__file__).with_name('ui.html')
    return p.read_text(encoding='utf-8') if p.exists() else '<h1>UI bulunamadı</h1>'
