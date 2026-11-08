# KRAL / ORBA — Stripe Live Acceptance Gate (2026-11-09)

**Scope**: branch-only, isolated Stripe webhook consumer for the existing Python KRAL server. **No production deployment, no payment execution, no live key, and no Google Play Billing implementation is claimed.**

## Verified account and deployment discovery

- Connected Stripe session returned **only** account acct_1TziZ4ECdWPb8N7p with livemode=false, display name "Mehmet Uğur cerdik sandbox". Listing its test subscriptions, invoices, customers, payment intents, charges, balance transactions, products and prices returned zero. **No statement about live merchant balance or purchases from other merchants follows from these results.**
- Railway MEHMET-YARATILIS-RUNTIME-v0-2-2, environment named production: latest deployments of mehmet-pwa-v022-runtime, mehmet-ai-backend-p1, mehmet-physical-acceptance-v022, mehmet-pwa-v022-repo returned FAILED; mehmet-pwa-v022 had no latest deployment status in the inventory. No persistent volumes were listed.
- Railway MEHMET-AI-STAGING production-named environment listed no services.
- Vercel/Macaly project lists returned empty in the connected accounts. **The actual ORBA AIOS production target was not established.**
- Google Play subscriber purchases and Apple consumer billing history are **not** Stripe merchant API resources; they require their own authorized provider statements. Google Play in-app digital sales require applicable Google Play Billing policy compliance.

## Code supplied

- server/stripe_billing.py: isolated stdlib HTTP webhook listener, HMAC SHA-256 Stripe-Signature verification, 300-second timestamp tolerance, strict event shape and STRIPE_LIVEMODE equality, SQLite transactionally recorded event IDs, and subscription status snapshots. Invoice receipts **never** grant access.
- server/tests/test_stripe_billing.py: ten deterministic tests. Importing the module neither starts the listener nor sends traffic.
- can_access is only a low-level, unauthenticated DB primitive: **do not** expose it in any owner, customer, or entitlement API. A distinct authenticated user-to-Stripe customer mapping and provider reconciliation are needed.

## Live acceptance gates — fail closed

1. Identify the **real live Stripe account** via an authorized Stripe-connected livemode=true context; verify merchant legal identity, country eligibility and minimum live permissions. Do not create, guess, copy or hard-code sk_live_*.
2. Provision a **live Stripe webhook endpoint** for a verified HTTPS production domain. Add a unique **live endpoint** whsec_* secret and STRIPE_LIVEMODE=true to a managed secret store. Keep all values out of git, logs, Android and Drive documents.
3. Deploy isolated listener behind HTTPS with restricted upstream ingress, port routing and a **private persistent volume** for BILLING_DB (absolute path). The current Railway environments show no confirmed healthy suitable deployment.
4. Verify endpoint ownership and perform live-mode *noncharging* test delivery/health and event redelivery checks; confirm signature rejection and deduplication under concurrency.
5. Add authenticated owner/customer-to-Stripe customer binding, live provider reconciliation using least-privileged server-side API credentials, event cursor/backfill, invoices, refunds, disputes, taxes, and access reversal. Block entitlements until that reconciliation exists.
6. Add checkout/pricing/portal only for **your own ORBA web products** and only after prices, tax, terms, merchant verification, charge/refund authorizations and external transactions are reviewed. Never charge stored customer cards from a generic assistant command.
7. Android in-app digital subscriptions are separate; use Google Play Billing with verified purchase tokens and backend acknowledgment. Do not treat Stripe as a Play billing bypass.
8. Owner review of account, actual production environment, new deployment plan, CI and secrets configuration. **Do not merge to main or deploy until these gates pass.**

## Local validation

From repository root, without network/keys:

    python -m unittest -v server.tests.test_stripe_billing
    python -m compileall -q server/stripe_billing.py server/tests/test_stripe_billing.py

CI verification of this exact GitHub branch must be checked separately; previous local ZIP tests do not establish CI success.

## Safety

STRIPE_WEBHOOK_SECRET is a Stripe webhook endpoint signing secret, not a Stripe API secret key. Key values should never appear in code or logs. A merchant's Stripe API does not list third-party payments from a different merchant's Stripe account. No live charging or subscription change is performed by this code.
