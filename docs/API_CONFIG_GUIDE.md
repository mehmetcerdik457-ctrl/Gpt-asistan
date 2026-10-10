# API and configuration guide

## Environment variables

- `KRAL_DB_PATH`: SQLite database path. The CLI defaults to
  `kral/safe/mem.db` next to its script; the modular core uses the same path.
- `KRAL_LOG_DIR`: directory for the CLI log. Defaults to `kral/safe/`.
- `KRAL_LOG_LEVEL`: desired log-level setting (defaults to `INFO`).
- `OPENAI_API_KEY`: optional credential. Never place a real key in source
  control. Configuration output reports only whether it is configured.
- `ENABLE_OFFLINE_MODE`: defaults to `true`. OpenAI is not selected while
  offline mode is enabled.
- `ENABLE_LOCAL_MODELS`: defaults to `true` as a capability preference; this
  does not mean a local model is implemented or installed.

Optional `.env` loading is supported when `python-dotenv` is installed.
Environment variables already set in the process take precedence. The
repository's `.env.example` contains empty placeholders; copy it to `.env` and
fill only local values if needed. `.env` and data/log artifacts are ignored by
Git.

Example:

```sh
export KRAL_DB_PATH="$HOME/.local/share/kral/mem.db"
export KRAL_LOG_DIR="$HOME/.local/state/kral"
python3 kral/safe/assistant.py
```

The application defaults to offline operation and performs no network calls
through `CoreEngine`. OpenAI API requests are only possible through the
optional adapter when an API key is configured and offline mode is disabled.
Local model inference is **NOT DONE**. Android UI/build verification,
Google Drive, and YouTube integration are also **NOT DONE**. The Android
workflow is not proof of a working app: `MainActivity.kt` and `res` resources
are not confirmed present.
