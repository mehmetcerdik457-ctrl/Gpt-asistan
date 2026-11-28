# KRAL Android Integration — 20 Oct 2026

Source reused from this repository: original Kotlin MainActivity, Gradle Android
project and the historical kral/safe/assistant.py command interface.
Original Termux SQLite table \`mem(id, ts, text)\` is mirrored in a **new**
Android-private \`kral_local.db\` without copying old user data or secrets.

## Implemented in this development branch
- Fixed malformed manifest, restricted package visibility to known Owner/Bridge
  IDs, denied Android backup and cleartext traffic.
- Turkish local commands: /kaydet, /liste, /soyle; task addition, listing,
  completion; Android TextToSpeech instead of Termux subprocess.
- Optional HTTPS OpenAI-compatible model transport. Requires a manually entered
  endpoint/model; no credential handling, automatic memory upload or tool calls.
- Owner and Bridge install/signature *read-only* check with preserved historical
  signer SHA-256. This is not real owner authentication.
- Privileged phone execution disabled by construction. No Accessibility,
  ROOT, Shizuku, shell, arbitrary Intent control, or bridge invocation.

## Explicitly not accepted
- No data migration from the old Python mem.db.
- No confirmed live LLM endpoint, vendor API key, or phone connection.
- No Owner/Bridge privileged IPC; debug build is not signed with the original
  Owner key. Signer matching an old record is only a heuristic.
- No real Samsung/Android device evidence. Debug APK is for development only.

CI: \`gradle :app:testDebugUnitTest :app:assembleDebug\`.
Original APKs, Golden Master and main branch are unchanged.
