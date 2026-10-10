# Kral Asistan

Kral Asistan is an early-stage, local-first personal assistant. Its working
component is a Python command-line interface backed by SQLite; the `core`,
`memory`, and `models` packages provide a small modular foundation. The
assistant works without an API key or network connection by default.

## Run the CLI

```sh
python3 kral/safe/assistant.py
```

Commands: `/kaydet <text>` saves a memory, `/liste` lists recent memories,
`/soyle <text>` attempts Termux text-to-speech, and `/cik` exits. Unprefixed
text continues to be saved and echoed as a simple response.

Set `KRAL_DB_PATH` to choose the SQLite database and `KRAL_LOG_DIR` to choose
the log directory. Defaults are `kral/safe/mem.db` and `kral/safe/`,
respectively. See [the configuration guide](docs/API_CONFIG_GUIDE.md) for the
modular core and optional API settings.

## Tests

```sh
python3 -m pip install -r requirements.txt
pytest -v
```

The Android build is known to be unverified: `MainActivity.kt` and Android
`res` resources are not confirmed present. See [project state](docs/PROJECT_STATE.md).
