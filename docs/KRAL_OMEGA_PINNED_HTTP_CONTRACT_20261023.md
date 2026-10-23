# KRAL/Omega physical-source integration contract (23 Oct 2026)

The existing KRAL PR #46 Kotlin health parser now consumes the **actual bytes**
of HTTP GET /api/health from pinned OMEGA PR #96 SHA fd34e1a6b57b13644c6f2053fe97e86b485de10b.
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
