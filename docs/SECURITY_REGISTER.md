# Security register

- **Exposed personal access token (PAT):** a PAT was previously pasted in
  chat and must be treated as exposed. Revoke it immediately and rotate any
  credentials or access that depended on it. No token value is reproduced
  here.
- **Secrets:** keep real credentials out of source, documentation, logs, and
  version control. `.env` is ignored; `OPENAI_API_KEY` is optional and never
  included in configuration serialization or status output.
- **Offline behavior:** offline mode is enabled by default. The core selects
  the network-capable adapter only when offline mode is disabled and an API
  key is configured.
- **Local data:** SQLite memory and exported JSON backups may contain
  sensitive user content. Protect backups and use `MemoryStorage.clear()` for
  explicit deletion.
- **Android:** build and UI security are unverified because
  `MainActivity.kt` and `res` resources are not confirmed present.
