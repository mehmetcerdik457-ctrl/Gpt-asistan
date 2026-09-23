---
applyTo: "**/*.kt,**/*.kts,**/AndroidManifest.xml,**/res/**"
---

# Android-specific instructions

When editing Android/Kotlin files in this repository:
- Preserve application identity, signing semantics, package names, and release behavior unless the task explicitly requires a change.
- Prefer lifecycle-aware APIs, structured concurrency, explicit null handling, and deterministic state transitions.
- Check manifest/exported-component implications whenever components, intent filters, providers, receivers, services, or permissions change.
- Check Android 12+ PendingIntent mutability and exported rules where relevant.
- Check modern background-execution and foreground-service restrictions where relevant.
- Avoid broad storage or accessibility permissions unless they are required by the task and justified by platform behavior.
- Never log tokens, credentials, personal data, signing data, or security-sensitive payloads.
- For networking changes, validate cleartext policy, TLS assumptions, certificate handling, timeouts, cancellation, and error paths.
- For WebView changes, review JavaScript bridges, file/content access, navigation control, URI validation, and mixed-content exposure.
- After implementation, run the available compile/test/lint tasks relevant to the changed module and inspect the real output.
