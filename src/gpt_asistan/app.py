from fastapi import FastAPI
from pydantic import BaseModel
from . import memory
from .provider import call_openai, offline_reply
import asyncio

app = FastAPI(title="GPT Asistan (Hafif)")

class Msg(BaseModel):
    session: str = "default"
    content: str

@app.on_event("startup")
def _startup():
    memory.init()

@app.post("/chat")
async def chat(m: Msg):
    memory.add(m.session, "user", m.content)
    hist = memory.history(m.session, limit=30)
    # OpenAI varsa kullan, yoksa yerel fallback
    ai = await call_openai(hist)
    if not ai:
        ai = offline_reply(hist)
    memory.add(m.session, "assistant", ai)
    return {"reply": ai, "tokens":"low", "session": m.session}
