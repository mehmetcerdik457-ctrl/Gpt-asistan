# ORBA Google Play subscriptions

The integration contains Android Billing 9 checkout, owner/device P-256 HTTP
requests, server-side Play verification and acknowledgement, owner-bound
PostgreSQL purchase storage, and authenticated Pub/Sub RTDN reconciliation.
Production configuration remains disabled by default. A local test result does
not establish live Google authorization, a production-signed app or a Play sale.

## Android purchase flow

Open **Google Play aboneliği** in the existing app and complete the device-owner
unlock. The app requests the account reference and product allowlist from the
configured HTTPS owner gateway. Product identifiers and prices are not entered
or invented by the client: eligible offers and all price phases come from
Google Play. Selecting an offer and confirming **Google Play'de satın al** starts
the native checkout only while the owner, endpoint and foreground scope remain
valid. The account binding and eligible offer are checked again before launch.

Purchase and restore callbacks are submitted through the existing enrolled
owner/device signatures. The app never grants entitlement from a client purchase
state or successful checkout launch. Refresh reconciles the currently owned
purchases with fresh backend verification. Mixed active and expired purchases
are summarized from the current reconciliation rather than the last callback.

Leaving the activity closes Billing and re-locks private content. Returning from
an explicitly launched checkout can reopen purchase status after a fresh owner
unlock; it never launches another purchase. No purchase token is persisted by
this UI. Android Keystore's existing 30-second authentication window is preserved;
after a long offer-browsing pause, close and reopen the subscription view for a
fresh unlock before retrying a signed request.

## Signed server contract

`POST /api/v1/owner/play/account` accepts only an empty JSON object, authenticated
by the existing dual-P256 boundary. It returns the protocol `contract`, a
64-character `obfuscated_account_id` and sorted `products` from the server's
configured allowlist. It performs no Google request and grants no entitlement.

`POST /api/v1/owner/play/verify` accepts only `productId` and `purchaseToken`.
The owner comes from verified signatures, never the request body. The server
performs fresh Google API verification, validates account binding, product,
state and expiry, acknowledges a verified purchase when necessary, and checks
the Google state again. A grant is returned only after durable ownership and
snapshot writes commit and the confirmed subscription remains unexpired.
Cached snapshots remain diagnostic; they do not grant access.

Canceled subscriptions can retain their confirmed paid entitlement until
expiry; active grace periods retain access. Pending, paused, on-hold and expired
purchases do not grant access. Boolean proof fields must be actual booleans.

Configuration and default-disabled runtime instructions are in
[ORBA_RUNTIME_CONFIGURATION.md](ORBA_RUNTIME_CONFIGURATION.md). Actual Play
product IDs, service accounts, credentials, Pub/Sub resources and backend host
must come from the authorized deployment; examples do not provision them.

## Validation

```sh
python -m pip install -r server/requirements.txt -r server/requirements-postgres.txt
python -m unittest discover -s server/tests -v
bash scripts/test_orba_rtdn_postgres.sh
./gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug --no-daemon
```

The PostgreSQL helper creates and removes its own disposable local container.
These checks use injected provider responses and synthetic credentials; they do
not make Play purchases or prove real Google-issued Pub/Sub token delivery.
Live Play lifecycle, production signing and existing-device upgrade acceptance
require separate real evidence. Existing encrypted app data and signing keys
must be preserved during that verification.
