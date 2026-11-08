# ORBA AIOS / KRAL Genesis — Stripe Billing Bridge (candidate)

Shared Python standard-library backend module, designed for the owner-gated KRAL/ORBA systems. **Tested locally; not deployed or connected to a live Stripe merchant account.** The repository branch is a review candidate; no production secrets should be committed. There is no attempt to read or pay subscriptions at unrelated merchants.

## Environment (server-side only)

- `STRIPE_WEBHOOK_SECRET` — Stripe endpoint secret `whsec_...`
- `STRIPE_EVENTS_DB` — absolute SQLite path on an existing PRIVATE PERSISTENT directory, e.g. `/data/stripe-events.sqlite3`
- `STRIPE_BIND=127.0.0.1` — loopback only
- `STRIPE_PORT=8091` — loopback port
- `STRIPE_SECRET_KEY` — `sk_test_...` or `sk_live_...`, only for explicit backend read-only calls to `list_merchant_subscriptions`. Never in APK, web UI, Git repo, or logs.

Run: `python -m stripe_bridge.billing`. Expose `POST /webhooks/stripe` only through an HTTPS reverse proxy with request-body preservation; configure the webhook endpoint in your Stripe Dashboard. No API key is needed for verifying webhooks; the separate Stripe endpoint secret is mandatory. Bind the service only to localhost; configure firewall and proxy separately. Store SQLite under a private volume. Restrict credentials to the billing worker. Do not enable automatic payments with this code.

## Event processing and guardrails

- Signature-verified against the exact raw body, HMAC SHA-256, 5-minute window; reject invalid events.
- SQLite durable event-id ledger, replay resistance, out-of-order event protection, no PAN/CVV/raw webhook persisted.
- `customer.subscription.created/updated/deleted` update merchant-only subscription state; `invoice.paid` cannot grant an entitlement. Access must also be checked against verified owner/device and app-specific product mapping before granting a permission; this module does NOT implement entitlement authorization.
- `list_merchant_subscriptions` is explicitly read-only and only scopes to the owner of the provided Stripe merchant key. It cannot see personal Google Play/Apple/other merchant subscriptions.
- No Stripe Connect or Google Play/Apple payment flows are simulated. Google Play purchase-token checks require the app publisher's entitlement; their developer API cannot access a user's entire personal Play order history. Apple StoreKit and App Store Server API must be integrated separately for app-owner purchases.
- For ORBA AIOS: import the shared module as a separate billing service. For KRAL Genesis: keep webhook secret and merchant key on its Python server, never Android. Use independent deployment DBs and keys per environment.

## Global launch gates

Stripe test mode, verified merchant KYB/KYC, webhook signature E2E, payout currency/tax/receipt configuration, refund/dunning process, privacy policy, terms, user consent/CMP, regional tax obligations, Google Play Billing if digital goods are sold inside Android, Apple IAP/StoreKit if sold through iOS, and ad-network app/site verification (including app-ads.txt where applicable). No production deployment or global advertising activation claimed.

## Test

`python -m unittest discover -s tests -v`