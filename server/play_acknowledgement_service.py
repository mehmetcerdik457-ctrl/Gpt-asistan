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
        snapshot_recorder=None) -> bool:
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

    def record_trusted(purchase):
        if snapshot_recorder is not None:
            # Called ONLY after trusted provider fetch + owner matching.
            # Storage failures fail the HTTP request closed (503), never grant.
            snapshot_recorder(
                db, purchase, server_secret=server_secret,
                observed_at_ms=now_ms)

    digest = token_digest(purchase_token)
    before = verify_and_map_subscription(
        purchase_token=purchase_token, access_token=access_token,
        owner_id=authenticated_owner_id, product_id=product_id,
        server_secret=server_secret, opener=opener,
    )
    if (not before.verified_by_google_api or
            access_phase(before.subscription_state, before.expires_at_ms, now_ms)
            == "DENIED"):
        record_trusted(before)
        return False

    if before.acknowledged:
        purchase = before
    else:
        # ACK only newly ACTIVE purchases. Existing canceled/grace subscriptions
        # may retain already-acknowledged access but must not trigger ACK POST.
        if before.subscription_state != "SUBSCRIPTION_STATE_ACTIVE":
            record_trusted(before)
            return False
        # Before ACK, only Play's known pending-ACK state may reach this path.
        # verify_and_map_subscription rejects unspecified/unknown ACK states.
        acknowledge_subscription(
            purchase_token=purchase_token, product_id=product_id,
            access_token=access_token, opener=opener,
        )
        # An HTTP 200 ACK is NOT a grant. Re-query and revalidate account,
        # product, expiry, and acknowledged state from the provider.
        purchase = verify_and_map_subscription(
            purchase_token=purchase_token, access_token=access_token,
            owner_id=authenticated_owner_id, product_id=product_id,
            server_secret=server_secret, opener=opener,
        )

    if not entitlement_allowed(
            purchase, owner_id=authenticated_owner_id,
            product_id=product_id, token_sha256=digest, now_ms=now_ms):
        record_trusted(purchase)
        return False
    bind_or_verify_owner(
        db, purchase_token=purchase_token,
        authenticated_owner_id=authenticated_owner_id, now_ms=now_ms,
    )
    # A positive snapshot is OBSERVATIONAL only. This request was authorized
    # using the fresh provider response above, NOT from the snapshot.
    record_trusted(purchase)
    return True
