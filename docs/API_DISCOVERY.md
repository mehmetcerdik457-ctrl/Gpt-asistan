# API discovery (değer içermez)

| Servis | Endpoint | Auth | Env değişkeni | Kullanıldığı dosya |
|---|---|---|---|---|
| OpenAI uyumlu LLM | `{LLM_BASE_URL}/chat/completions` (varsayılan `https://api.openai.com/v1`) | ****** | `OPENAI_API_KEY` | `core/llm.py`, `core/config.py` |
| Yerel LLM (Ollama/llama.cpp) | `http://localhost:11434/v1` / `:8080/v1` | yok / isteğe bağlı | `LOCAL_LLM_API_KEY` | `core/llm.py` |
| Google Drive API v3 | `files.create` | Servis hesabı veya OAuth | `GDRIVE_SERVICE_ACCOUNT_JSON`, `GDRIVE_OAUTH_TOKEN_JSON`, `GDRIVE_FOLDER_ID` | `backup/backup_to_drive.py` |
| rclone (Drive) | rclone remote | rclone config | `RCLONE_REMOTE` | `backup/backup_to_drive.sh` |
| Sentry / PyPI / npm / Docker Hub / Android signing | - | token/parola | `SENTRY_DSN`, `PYPI_API_TOKEN`, `NPM_TOKEN`, `DOCKERHUB_USERNAME`, `DOCKERHUB_PASSWORD`, `ANDROID_*` | yalnızca `.env.example`'da listeli; bu repoda kullanımı yok |

Android uygulaması ve `agents/kral_safe` herhangi bir ağ API'si çağırmaz. Diğer repolar taranmadı.
