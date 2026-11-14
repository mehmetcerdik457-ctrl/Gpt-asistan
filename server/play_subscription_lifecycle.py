"""Conservative Google Play SubscriptionPurchaseV2 access lifecycle policy.

The state and expiry MUST originate from fresh, trusted Play Developer API
responses; this module cannot create an entitlement or trust client input.
See Google Play subscription lifecycle documentation.
"""

ACCESS_STATES = frozenset((
    "SUBSCRIPTION_STATE_ACTIVE",
    "SUBSCRIPTION_STATE_IN_GRACE_PERIOD",
    "SUBSCRIPTION_STATE_CANCELED",
))


def access_phase(subscription_state, expires_at_ms, now_ms):
    """Returns a distinct access phase, or 'DENIED'. Never extends expiry.

    A canceled subscription remains paid-through-expiry. Grace period remains
    entitled if Google's current, trusted expiry is still in the future.
    Account hold, paused, expired, pending and unknown states have no access.
    """
    if (not isinstance(subscription_state, str) or
            not isinstance(expires_at_ms, int) or isinstance(expires_at_ms, bool) or
            not isinstance(now_ms, int) or isinstance(now_ms, bool) or
            now_ms < 0 or expires_at_ms <= now_ms):
        return "DENIED"
    if subscription_state == "SUBSCRIPTION_STATE_ACTIVE":
        return "ACTIVE"
    if subscription_state == "SUBSCRIPTION_STATE_IN_GRACE_PERIOD":
        return "GRACE_PERIOD"
    if subscription_state == "SUBSCRIPTION_STATE_CANCELED":
        return "CANCELED_PAID_THROUGH_EXPIRY"
    return "DENIED"
