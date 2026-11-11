"""Explicit, fail-closed server-side ACK then *fresh* subscription verification.

This service is NOT a public HTTP endpoint. Caller MUST authenticate the owner,
get OAuth via a secure credential provider and use server-controlled clock.
No checkout, Play Console or real payment is exercised by offline tests.
"""
from __future__ import annotations

from server.play_acknowledgement import acknowledge_subscription
from server.play_entitlement_gate import entitlement_allowed, token_digest
from server.play_owner_binding import bind_or_verify_owner
from server.play_subscription_mapper import verify_and_map_subscription


def acknowledge_then_verify_subscription(
        *, db, purchase_token: str, access_token: str,
        authenticated_owner_id: str, product_id: str,
        server_secret: bytes, now_ms: int, opener=None) -> bool:
    """True only after fresh provider ACK, active entitlement and owner binding.

    Pending payment, expiry, wrong account/product, failed ACK, and missing
    provider confirmation MUST NOT create an owner binding or paid access.
    """
    if not isinstance(authenticated_owner_id, str) or not authenticated_owner_id.strip():
        raise ValueError("INVALID_AUTHENTICATED_OWNER")
    if not isinstance(server_secret, bytes) or len(server_secret) < 32:
        raise ValueError("INVALID_SERVER_SECRET")
    if not isinstance(now_ms, int) or isinstance(now_ms, bool) or now_ms < 0:
        raise ValueError("INVALID_SERVER_TIMESTAMP")
    digest = token_digest(purchase_token)
    before = verify_and_map_subscription(
        purchase_token=purchase_token, access_token=access_token,
        owner_id=authenticated_owner_id, product_id=product_id,
        server_secret=server_secret, opener=opener,
    )
    if (not before.verified_by_google_api
            or before.subscription_state != "SUBSCRIPTION_STATE_ACTIVE"
            or not isinstance(before.expires_at_ms, int)
            or before.expires_at_ms <= now_ms):
        return False

    if before.acknowledged:
        purchase = before
    else:
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
        return False
    bind_or_verify_owner(
        db, purchase_token=purchase_token,
        authenticated_owner_id=authenticated_owner_id, now_ms=now_ms,
    )
    return True
