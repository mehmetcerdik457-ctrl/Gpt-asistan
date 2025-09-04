from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from .provider import call_openai, offline_reply
SYS_TR = 'HER ZAMAN TÜRKÇE CEVAP VER. Uzun değil, net ol.'

SYS_TR='HER ZAMAN TÜRKÇE CEVAP VER. Uzun değil, net ol.'
from .memory import build_system_prompt
import time, json

r = APIRouter()

@r.get("/v1/models")
def models():
    return {"object":"list","data":[{"id":"ga-local","object":"model"}]}

class ChatMsg(BaseModel):
    role:str; content:str

class ChatReq(BaseModel):
    model:str="ga-local"
    messages:List[ChatMsg]
    temperature:Optional[float]=0.3
    stream: Optional[bool] = False

def make_json_resp(txt:str, model:str)->Dict[str,Any]:
    return {
        "id":"ga-chat-1",
        "object":"chat.completion",
        "created":int(time.time()),
        "model": model,
        "choices":[{"index":0,"message":{"role":"assistant","content":txt},"finish_reason":"stop"}],
        "usage":{"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}
    }

def make_stream(txt:str, model:str):
    # minimal SSE compatible with OpenAI chat.completions
    def gen():
        pre={"id":"ga-chat-1","object":"chat.completion.chunk","created":int(time.time()),"model":model}
        yield "data: " + json.dumps({**pre,"choices":[{"index":0,"delta":{"role":"assistant"}}]}) + "\n\n"
        for piece in [txt[i:i+40] for i in range(0,len(txt),40)]:
            yield "data: " + json.dumps({**pre,"choices":[{"index":0,"delta":{"content":piece}}]}) + "\n\n"
        yield "data: " + json.dumps({**pre,"choices":[{"index":0,"delta":{}}],"finish_reason":"stop"}) + "\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")

@r.post("/v1/chat/completions")
async def chat_completions(body: ChatReq):
    hist=[{"role":"system","content":SYS_TR}] + [m.model_dump() for m in body.messages]
    hist=[{"role":"system","content":SYS_TR}] + hist
    if SYS_TR:
        hist=[{"role":"system","content":SYS_TR}] + hist
    sys = build_system_prompt()
    hist = ([{"role":"system","content":sys}] + hist) if sys else hist
    sys = build_system_prompt()
    hist = ([{"role":"system","content":sys}] + hist) if sys else hist
    txt=await call_openai(hist) or offline_reply(hist)
    if body.stream:
        return make_stream(txt, body.model)
    return make_json_resp(txt, body.model)
SYS_TR = 'HER ZAMAN TÜRKÇE CEVAP VER. UZATMADAN, NET YANIT VER.'
