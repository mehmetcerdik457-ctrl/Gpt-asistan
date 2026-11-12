# ORBA Google Play Billing — Production Acceptance Gate

Status: **HOLD — offline verification prototype only**. This document does not authorize publishing, billing, or entitlement activation.

## Verified in this branch
- Server-side read-only subscriptionsv2 API adapter with explicit errors and response-size limit.
- Server-side HMAC account identifier, strict account identifier comparison against Play response.
- Fail-closed entitlement decision (currently ACTIVE + ACKNOWLEDGED + unexpired only).
- SQLite token digest ownership binding (not a substitute for verified account binding).
- Offline simulated provider responses, negative tests, and branch-specific GitHub Actions CI.

## Mandatory blockers before production
1. **Android BillingClient**: integrate official current Google Play Billing Library into the real app; query ProductDetails, handle purchases and pending purchases, and set the server-provided obfuscatedAccountId when launching billing flow. Verify current Play policies and supported library version at implementation time.
2. **Authentication**: authenticated backend session; derive owner ID from validated session claims only. Do not accept arbitrary owner_id from request JSON, URL or headers.
3. **Account identifier delivery**: authenticated, rate-limited endpoint returning HMAC-derived opaque identifier; secret kept only in a server-side secret manager; rotation/migration plan required.
4. **Google Publisher API**: actual authorized service-account OAuth and Play Console API access. Verify the Android package, products, subscriptions, base plans and test license configuration.
5. **Purchase processing**: POST token to authenticated backend over TLS; use the verification service, check Play account binding, then store token digest and ownership in a protected durable database. Never store or log raw tokens in analytics or application logs.
6. **Acknowledgement**: implement and test prompt acknowledgement of valid new purchases using official API/Library. The current conservative gate denies unacknowledged purchases and has no acknowledgement operation.
7. **Lifecycle**: explicitly design canceled-but-paid, grace period, account hold, pause, refund, revoke, restore, upgrade/downgrade, token replacement, duplicate RTDN and out-of-order RTDN. Current gate only allows ACTIVE, so it may deny legitimate paid access in some lifecycle states.
8. **RTDN**: authenticated Pub/Sub push verification and idempotent reconciliation against fresh Play API state; never grant access based only on an RTDN message.
9. **Database operations**: production PostgreSQL or protected durable database, backups, migrations, transaction isolation, retention, unique constraints, multi-process contention and recovery testing. SQLite in-memory unit tests do not establish production readiness.
10. **End-to-end acceptance**: Play license test account, internal testing track, actual Android device(s), signed AAB, Play-distributed test install, real test purchase and renewal/refund/revoke simulations; capture redacted evidence.
11. **Security review**: threat model, session fixation/replay, account takeover, secret rotation, least-privilege service credentials, rate limits, logging redaction, concurrency and dependency scanning.
12. **Owner release approval**: explicit authorization for any main merge, Play Console change, release signing, publication, or production billing activation.

## Evidence rules
- CI PASS is evidence of only the jobs and tests actually run.
- The generic Android CI/build jobs may be SKIPPED on this branch; that is not Android build success.
- No real Play API call, live payment, or real device purchase has been demonstrated by this branch.
- Count tests by current unique suite, not by summing successive CI reruns.
- Keep Stripe and OMEGA PostgreSQL mock suites separate; their success is not proof of Google Play live billing.

## Release decision
**PRODUCTION HOLD** until every blocker is evidenced and explicitly approved by the owner.


## 12 Nov 2026 — ACK-then-reverify candidate (stacked PR; not deployed)

An isolated **server-only** acknowledgement adapter is provided in
`server/play_acknowledgement.py` and a caller-gated orchestration function
in `server/play_acknowledgement_service.py`. The candidate calls the official
Google Play `purchases.subscriptions.acknowledge` endpoint *only after*
a fresh, verified `subscriptionsv2.get` response matches authenticated
owner's obfuscated account identifier, product, ACTIVE state and unexpired
entitlement. When ACK is pending, an HTTP 200 response is **not** treated
as a subscription grant: the provider must be fetched a second time and
return ACKNOWLEDGED before durable owner binding.

Negative tests use fully fake provider responses and assert no grants for
pending payment, expired, owner mismatch, product mismatch, HTTP/network
errors, lost acknowledgement confirmation or provider changes on refresh.
Unknown acknowledgement states still deny. Android checkout start, secure
production OAuth/session endpoints, Google license tests, RTDN, refund/hold
lifecycle, signed release and real payment remain **NOT IMPLEMENTED /
NOT VERIFIED**. Never expose this function as an unauthenticated route.


## 12 Nov 2026 — Android Billing 9 checkout connector (stacked draft)
`PlayBillingConnector` can now query fresh Google Play SUBS `ProductDetails`
and available subscription offers; only an explicitly selected exact offer
token is used for `launchBillingFlow`, always invoked on the Android main
thread. `BillingFlowParams.setObfuscatedAccountId` receives a validated
64-character lowercase HMAC-derived identifier that **must be fetched from
a trusted authenticated backend**; no key or owner PII is embedded in APK.
Feature availability, service readiness, stale offer and malformed checkout
requests fail closed.

**Critical:** These APIs are NOT yet wired to a customer-facing screen, a
backend authenticated transport, real Play Console configured offers, or a
production OAuth/ack/RTDN flow. Android JVM unit tests cover input contracts,
not a device purchase. Launch success is not payment success, nor entitlement
proof. Only the verified backend may grant rights. Keep PRODUCTION HOLD.


## 12 Nov 2026 — Protected owner-gateway HTTP boundary, stacked DRAFT
Adds `POST /api/v1/owner/play/account` and
`POST /api/v1/owner/play/verify` under **existing dual-P256
owner/device signatures, nonce replay rejection, path/body hash binding**.
They never trust a client-provided owner, entitlement flag, Google
response, or timestamp. The verified owner identity is passed from the
HTTP signature gate, not parsed from JSON.

The Play adapter accepts only an **explicit server-installed**
`PlayGatewayBoundary` with a 32+ byte server-only HMAC secret, a
specific product allowlist, a trusted OAuth supplier, and a private
pre-migrated durable DB factory. These components and live credentials
are **NOT INSTALLED** by the entrypoint. Every Play API path additionally
requires explicit `ORBA_PLAY_BOUNDARY_ENABLED=YES`; otherwise it
fails closed with HTTP 503. JWT-less direct JSON, unsigned requests,
malformed product/token and signed nonce replay cannot access Play.
Result bodies contain only boolean entitlement / opaque account ID.
The genuine P-256 localhost HTTP tests exercise both signature denial
and offline mocked Play provider flows, with zero actual payments.

**Not production ready:** No Play Console API OAuth provisioning,
rate limit persistence, public HTTPS configuration, Play-licensed device
purchase, multi-account identity design, backend-to-Android deployed
transport, RTDN, recovery, signed release or explicit owner deployment
approval. These routes are single-owner-specific and are NOT a generic
consumer identity system. No rollout or real Google API call conducted.

## 12 Nov 2026 — Android signed owner Play transport

Android `OmegaEnvelope` now permits signing exactly `/play/account` and
`/play/verify` through the EXISTING AndroidKeystore dual-P256 owner and
device keys. `OwnerGateway.playAccountId()` fetches the server-generated
obfuscated account identifier only from the configured HTTPS endpoint;
`OwnerGateway.verifyPlayPurchase()` sends only validated productId and
purchaseToken with the existing signed request transport. Both methods
require the selected base URL to equal the previously configured endpoint
and must run off the main/UI thread. Response parsing fails closed if
contract, hex account ID, entitlement boolean, or verification provenance
is wrong; HTTP 200 alone does not grant subscriptions.

This is an adapter, not an active purchase flow: no UI call site, real
backend provisioning, production OAuth, RTDN or live Play license test.
Android JVM contract tests exercise signing canonicalization and response
parsing only; they do not invoke biometrics on physical devices.
