# Project state

The working feature is the local SQLite-backed command-line assistant in
`kral/safe/assistant.py`. The modular `core`, `memory`, and `models` Python
packages support local memory operations and default to offline behavior.

Status:

- CLI memory save/list, Termux TTS attempt, configurable DB/log paths: present.
- Core configuration and SQLite memory backup/restore: present.
- OpenAI access: optional adapter, disabled in offline mode and not selected
  without an API key.
- Local model inference: **NOT DONE**; see `LOCAL_MODELS.md`.
- Android UI/build: **NOT DONE / unverified**. `MainActivity.kt` and Android
  `res` resources are not confirmed present. The Android build is known to be
  unverified.
- Google Drive integration: **NOT DONE**.
- YouTube integration: **NOT DONE**.
