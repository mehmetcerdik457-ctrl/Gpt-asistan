# KRAL Android ↔ PROJECT OMEGA status check (23 October 2026)

Existing preview app: Gpt-asistan DRAFT PR #46, stacked on PR #39.
OMEGA backend source: benim-uygulamam DRAFT PR #96.

The app already has a signed OwnerGateway connecting to **KRAL server**
POST /api/v1/owner/models and POST /api/v1/owner/chat. These routes are **not**
the same as OMEGA PR96's /api/health and /api/owner/status. Therefore simply
entering an OMEGA URL into the KRAL model field does NOT integrate both servers.

This patch adds one button on the existing unlocked KRAL preview screen:
"OMEGA durumunu kontrol et (salt okunur)". Only after the user enters a
HTTPS root URL does it issue GET /api/health, with no signing keys, cookies,
owner registration, model requests, history or memory. It does not persist URL.
It refuses redirects, non-JSON, oversized bodies, HTTP failure, unexpected
status, and any response asserting owner_identity_verified or execution_enabled
true. The UI explicitly states that **even a received HTTPS health status is
NOT verified owner enrollment, production readiness, or device authorization**.
Both server-side flags must be the literal JSON boolean false to show status.

The implementation consumes OMEGA's **existing** health shape without modifying
OMEGA's execution guards, provider API or backend routes. Synthetic JVM tests
check fail-closed logic; a real HTTPS-host/device test and complete Owner
wire protocol are still BLOCKED.

No physical Android test, release signer or model execution is implied.
Never install preview over existing signed Owner/CİHAT or previous preview
without compatible signing/data proof. Do not merge to main.
