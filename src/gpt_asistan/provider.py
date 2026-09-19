import os

import httpx

OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE = os.getenv("OPENAI_BASE", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


async def call_openai(messages):
    if not OPENAI_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{OPENAI_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_KEY}"},
                json={"model": OPENAI_MODEL, "messages": messages, "temperature": 0.3},
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
    except Exception:
        return None


def offline_reply(messages):
    # Ultra hafif yerel fallback: son kullanıcı mesajına kural tabanlı kısa yanıt
    user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    if not user.strip():
        return "Merhaba! Ne yapmak istersin?"
    if any(w in user.lower() for w in ["hata", "error", "bug"]):
        return "Hata ayıklamada yardımcı olabilirim. Adımları ve hata çıktısını paylaş."
    if "apk" in user.lower():
        return "Android APK için imza/keystore ve build adımlarını kurabiliriz."
    return "Not ettim. İstersen ayrıntı ver, kısa plan çıkarayım."
