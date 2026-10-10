# Repository inventory

This inventory describes files present in the repository:

- `kral/safe/assistant.py`: Python command-line memory assistant using SQLite
  and optional Termux text-to-speech.
- `core/`: runtime environment configuration and assistant orchestration.
- `memory/`: SQLite persistence and JSON backup/restore.
- `models/`: offline stub, guarded OpenAI adapter, and unimplemented local
  model placeholder.
- `tests/`: pytest coverage for the CLI, configuration, engine, and storage.
- `app/src/main/AndroidManifest.xml`, Gradle settings/build files, and
  `.github/workflows/android.yml`: Android/Gradle project metadata and build
  workflow. The expected `MainActivity.kt` and `res` files are not confirmed
  present.
- `.github/workflows/ci.yml`: Python test workflow.
- `.env.example`: empty-value environment-variable placeholders.

No Google Drive or YouTube integration exists in this inventory.
