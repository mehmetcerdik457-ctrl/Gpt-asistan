# Gpt-asistan monorepo

Mehmet Cerdik'in kendi projeleri için monorepo.

| Dizin | İçerik |
|---|---|
| `core/` | Sağlayıcı-bağımsız LLM istemcisi (OpenAI uyumlu / yerel), yapılandırma yükleyici, araç/ajan kayıt sistemi |
| `agents/` | Ajanlar (`kral_safe`: SQLite hafızalı yerel Termux asistanı) |
| `integrations/` | Dış servis entegrasyonları (şu an boş) |
| `apps/` | Uygulama notları. Android uygulaması Gradle yapılandırması nedeniyle kökteki `app/` altında kalır, bkz. `apps/README.md` |
| `tools/` | Yardımcı araçlar (şu an boş) |
| `archive/` | Çakışan/eskimiş içerik için (şu an boş) |
| `backup/`, `evidence/` | Google Drive yedekleme ve kanıt/log üretimi |
| `docs/` | INVENTORY, API_DISCOVERY, SECURITY_FINDINGS, KNOWN_ISSUES, MIGRATION_REPORT |

Harici/fork projeler kopyalanmaz; bkz. [`MANIFEST.md`](MANIFEST.md).

## Bağımsızlık hakkında dürüst not
`core/` bir model **içermez**. Bir LLM uç noktasına bağlanır: OpenAI uyumlu bulut API'si (`LLM_PROVIDER=openai`, `OPENAI_API_KEY`)
veya yerel uç nokta (`LLM_PROVIDER=local`, varsayılan Ollama `http://localhost:11434/v1`; llama.cpp için `LLM_BASE_URL=http://localhost:8080/v1`).
Dış servislere tam bağımsızlık için yerel bir modelin kurulup yapılandırılması gerekir.

## Kullanım
```
cp .env.example .env     # değerleri kendiniz doldurun, commit etmeyin
python -m unittest discover -s tests
bash scripts/validate_structure.sh
python agents/kral_safe/assistant.py
```
```python
from core import load_config, LLMClient
print(LLMClient(load_config()).chat([{"role": "user", "content": "Merhaba"}]))
```
