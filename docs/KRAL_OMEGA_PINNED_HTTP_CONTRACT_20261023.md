# KRAL/Omega physical-source integration contract (23 Oct 2026)

The existing KRAL PR #46 Kotlin health parser now consumes the **actual bytes**
of HTTP GET /api/health from pinned OMEGA PR #96 SHA 46894ad9d87ad7c75c3c51e003b1931e890199c4.
A GitHub CI workflow checks out both exact commits with no credential persistence,
runs the real OMEGA Python HTTP handler on runner loopback, saves the raw
HTTP body and sha256, asserts GET /api/models and POST /api/chat return HTTP
403 OWNER_EXECUTION_NOT_APPROVED, then tests the real Android Kotlin
OmegaReadOnlyStatus parser with those actual response bytes.

This is meaningful cross-repo backend-to-client **wire-contract testing**.
The Kotlin JVM test receives response bytes through a test HttpURLConnection
object. No Android TLS socket, physical device, real enrolled Owner,
real provider, private memory, or live phone/server integration is tested.
It must never be counted as full 100-item or production acceptance.

All provider keys are synthetic placeholders; no user secrets or live
model requests. Source pinned immutably. main unchanged.

\nNew CI addition: real synthetic dual-P256 Owner/Device signed POST
/api/v1/owner/models matches the existing KRAL OmegaEnvelope.MODELS
canonical signature, returns hard 403 OWNER_EXECUTION_NOT_APPROVED, and exact
replay is denied by SQLite nonce store. No real Owner keys, model list or
provider calls. This closes the former 404 endpoint mismatch while refusing
execution until physical Owner enrollment and approval.\n