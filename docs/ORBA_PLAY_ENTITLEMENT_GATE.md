# ORBA Google Play entitlement decision candidate

**Status: OFFLINE ONLY / NOT GOOGLE-VERIFIED / NOT PRODUCTION READY.**

This is a pure Python decision core, not a Google Play Developer API adapter,
BillingClient, RTDN consumer, authenticated endpoint, purchase acknowledgement
service, or deployed entitlement system. A client must never supply a
`VerifiedPlayPurchase` object as trusted evidence. The actual server adapter
must verify purchase token, package, product, subscription state, expiry,
acknowledgement and user binding against Google Play's authorized API.

The initial gate deliberately permits only ACTIVE, acknowledged, unexpired
purchases with an explicit trusted-verifier flag. This is **conservative** and
not a complete Play policy implementation: canceled subscriptions may retain
entitlement until expiry, grace periods and paused states require explicit
policy and Google Play documentation checks. Do not ship this restrictive
decision function as the complete production subscription policy.

No tokens, live credentials, payment actions, or provider calls are included.
Run: `python -m unittest -v server.tests.test_play_entitlement_gate`.
Owner review and full provider-backed tests are required before deployment.
