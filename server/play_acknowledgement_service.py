"""Explicit, fail-closed server-side ACK then *fresh* subscription verification.

This service is NOT a public HTTP endpoint. Caller MUST authenticate the owner,
get OAuth via a secure credential provider and use server-controlled clock.
No checkout, Play Console or real payment is exercised by offline tests.
"""
from __future__ import annotations

from server.play_acknowledgement import acknowledge_subscription
from server.play_entitlement_gate import entitlement_allowed, token_digest
from server.play_subscription_lifecycle import access_phase
from server.play_owner_binding import bind_or_verify_owner
from server.play_subscription_mapper import verify_and_map_subscription


def acknowledge_then_verify_subscription(
        *, db, purchase_token: str, access_token: str,
        authenticated_owner_id: str, product_id: str,
        server_secret: bytes, now_ms: int, opener=None,
        snapshot_recorder=None, owner_binder=None, clock_ms=None,
        verified_observer=None) -> bool:
    """True only after current provider verification and strict owner binding.

    Already-acknowledged canceled (paid-through-expiry) and grace-period
    subscriptions retain benefits per Play policy. Only an ACTIVE purchase
    with pending ACK can trigger a new provider acknowledgement.
    """
    if not isinstance(authenticated_owner_id, str) or not authenticated_owner_id.strip():
        raise ValueError("INVALID_AUTHENTICATED_OWNER")
    if not isinstance(server_secret, bytes) or len(server_secret) < 32:
        raise ValueError("INVALID_SERVER_SECRET")
    if not isinstance(now_ms, int) or isinstance(now_ms, bool) or now_ms < 0:
        raise ValueError("INVALID_SERVER_TIMESTAMP")
    if snapshot_recorder is not None and not callable(snapshot_recorder):
        raise ValueError("SNAPSHOT_RECORDER_INVALID")
    if owner_binder is not None and not callable(owner_binder):
        raise ValueError("OWNER_BINDER_INVALID")
    if clock_ms is not None and not callable(clock_ms):
        raise ValueError("SERVER_CLOCK_INVALID")
    if verified_observer is not None and not callable(verified_observer):
        raise ValueError("VERIFIED_OBSERVER_INVALID")
    last_time = now_ms

    def current_time():
        nonlocal last_time
        value = clock_ms() if clock_ms is not None else now_ms
        if (type(value) is not int or not 0 <= value <= 4102444800000 or
                value < last_time):
            raise ValueError("SERVER_CLOCK_INVALID")
        last_time = value
        return value

    def record_trusted(purchase, observed_at_ms):
        if snapshot_recorder is not None:
            # Called ONLY after trusted provider fetch + owner matching.
            # Storage failures fail the HTTP request closed (503), never grant.
            snapshot_recorder(
                db, purchase, server_secret=server_secret,
                observed_at_ms=observed_at_ms)

    digest = token_digest(purchase_token)
    observed_at_ms = current_time()
    before = verify_and_map_subscription(
        purchase_token=purchase_token, access_token=access_token,
        owner_id=authenticated_owner_id, product_id=product_id,
        server_secret=server_secret, opener=opener,
    )
    decision_ms = current_time()
    if (not before.verified_by_google_api or
            access_phase(before.subscription_state, before.expires_at_ms, decision_ms)
            == "DENIED"):
        record_trusted(before, observed_at_ms)
        return False

    if before.acknowledged:
        purchase = before
    else:
        # ACK only newly ACTIVE purchases. Existing canceled/grace subscriptions
        # may retain already-acknowledged access but must not trigger ACK POST.
        if before.subscription_state != "SUBSCRIPTION_STATE_ACTIVE":
            record_trusted(before, observed_at_ms)
            return False
        # Before ACK, only Play's known pending-ACK state may reach this path.
        # verify_and_map_subscription rejects unspecified/unknown ACK states.
        acknowledge_subscription(
            purchase_token=purchase_token, product_id=product_id,
            access_token=access_token, opener=opener,
        )
        # An HTTP 200 ACK is NOT a grant. Re-query and revalidate account,
        # product, expiry, and acknowledged state from the provider.
        observed_at_ms = current_time()
        purchase = verify_and_map_subscription(
            purchase_token=purchase_token, access_token=access_token,
            owner_id=authenticated_owner_id, product_id=product_id,
            server_secret=server_secret, opener=opener,
        )
        decision_ms = current_time()

    if not entitlement_allowed(
            purchase, owner_id=authenticated_owner_id,
            product_id=product_id, token_sha256=digest, now_ms=decision_ms):
        record_trusted(purchase, observed_at_ms)
        return False
    binder = owner_binder if owner_binder is not None else bind_or_verify_owner
    binder(
        db, purchase_token=purchase_token,
        authenticated_owner_id=authenticated_owner_id, now_ms=decision_ms,
    )
    # A positive snapshot is OBSERVATIONAL only. This request was authorized
    # using the fresh provider response above, NOT from the snapshot.
    record_trusted(purchase, observed_at_ms)
    # Waiting for an ownership/snapshot row lock can outlive the subscription.
    # Fail the caller-owned transaction rather than returning a stale grant.
    if not entitlement_allowed(
            purchase, owner_id=authenticated_owner_id, product_id=product_id,
            token_sha256=digest, now_ms=current_time()):
        raise ValueError("PLAY_VERIFICATION_EXPIRED")
    if verified_observer is not None:
        verified_observer(purchase)
    return True
