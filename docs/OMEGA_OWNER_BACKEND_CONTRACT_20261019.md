# OMEGA / Owner Android transport contract — 2026-10-19 (DRAFT, NOT ACCEPTED)

Sources:
- Owner 1.5.4, `Gpt-asistan` PR #32 HEAD `a82c8f02a34d9f30c99cf60c854bb68de7511764`.
- Public MEHMET AI backend, `benim-uygulamam` PR #87 HEAD `bdfbb7822bf83a9b8543930e982a0f029cc416e6`.
- These are NOT the same runtime, package, or branch. The public backend is `http.server` based, not FastAPI; do not label it a running FastAPI integration.

## Current transport (verified code path; live external DNS not verified)
Owner sends HTTPS POST to exact `https://api.openai.com/v1/responses` with a device-keystore-protected provider secret. Endpoint policy denies different hosts, redirects and non-TLS URLs. The secret is stored locally, not copied into GitHub/Drive. `secret_configured=true` only means an encrypted stored value is present, not a successful decrypt or model response.

## Proposed next-version, SERVER-ONLY API contract (NOT IMPLEMENTED)
Before any Owner-to-OMEGA remote call, implement owner-bound, replay-resistant authentication and a verified server trust policy. **Never substitute `secret_configured`, bridge availability, device ID or UI boolean for identity.**
- `GET /api/health` => service status only; does not imply provider availability.
- `GET /api/models` => allowlisted live models, errors fail closed without tokens.
- `POST /api/chat` JSON: `{"message":"...","provider":"openai","attachments":[]}` and request ID. Server-side key only; cap payload/token costs; no secrets in URL/logs.
- `POST /api/research` returns 501 `RESEARCH_PROVIDER_UNCONFIGURED` until a real provider is provisioned.
- High-risk phone actions remain in the separate authenticated Owner+Bridge channel. CİHAT remains a distinct worker package `com.codespaceapps.aichat` and receives only authorized user-bound prompts.

## Security requirements
The server is NOT yet a trusted owner-auth endpoint, so Android must NOT redirect provider calls or send its local API key to it until signed owner enrollment, certificate/pinning policy, permissions, cost limits, and real end-to-end negative tests exist. A later adapter will negotiate endpoint/version and reject incompatible backends, preserving original signed APK unchanged.

## Codes and next observations
- `FRESH_OWNER_AUTH_REQUIRED_FOR_PROVIDER_SECRET`: prompt fresh biometric/device credential before provider-bound calls. Do not downgrade Keystore.
- `PROVIDER_DNS_UNAVAILABLE`: capture sanitized network capability, DNS mode, connectivity and timing on the actual authorized device. It does NOT prove key invalidity or an OpenAI outage.
- `PROVIDER_NETWORK_TIMEOUT`, `PROVIDER_CONNECT_FAILED`, `PROVIDER_TLS_FAILURE`: distinct diagnostic classes; all fail closed.
- D4 and D5 are separate local archives; passing historical tests does not validate this app.
