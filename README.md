# gpt-asistan (hafif)
- **Hafıza:** SQLite (`memory.db`)
- **API:** FastAPI `/chat`
- **CLI:** `ga "mesaj"`
- **Çalıştır:** `uvicorn gpt_asistan.app:app --reload`
- **Çevrimdışı fallback:** yerel kural tabanlı cevap (API anahtarı yoksa bile).
