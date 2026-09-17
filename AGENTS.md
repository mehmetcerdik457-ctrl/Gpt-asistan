# Agent Execution Rules

These rules apply to AI agents working in this repository.

- Inspect the real repository, current branch, open pull request, and latest workflow evidence before changing code.
- Preserve existing verified work. Do not reset working branches or replace evidence with plans.
- Never claim PASS for a build, test, APK, signing, hash, runtime behavior, security scan, MCP call, or cloud operation without direct tool output.
- For Android changes, execute the strongest available Gradle build and preserve the exact failure log when it fails.
- Treat APK/APKM inputs as immutable evidence. Never patch, repack, resign, zipalign, or overwrite an original forensic target.
- Keep public APK forensic work separate from Owner Edition work.
- Do not commit secrets, tokens, private keys, signing keystores, passwords, or production credentials.
- Prefer read-only access when it is sufficient. Separate development, security-review, signing, and release privileges.
- When a path fails, diagnose the concrete root cause and try a technically distinct fallback before declaring BLOCKED.
- Reuse previous verified findings rather than presenting them as new progress.
- For release artifacts, bind filename, byte size, SHA-256, commit SHA, workflow run, and provenance evidence.
