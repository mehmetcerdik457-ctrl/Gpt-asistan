"""Fail-closed orchestration for Play verification, entitlement and ownership.

Only invoke after trusted session authentication. No production HTTP route,
credential issuance, BillingClient, or live purchases are implemented here.
"""
from server.play_entitlement_gate import entitlement_allowed, token_digest
from server.play_subscription_mapper import verify_and_map_subscription
from server.play_owner_binding import bind_or_verify_owner


def verify_play_entitlement(*, db, purchase_token: str, access_token: str,
                            authenticated_owner_id: str, product_id: str,
                            server_secret: bytes, now_ms: int, opener=None) -> bool:
    """No owner binding is written unless provider, account and entitlement pass."""
    if not isinstance(authenticated_owner_id, str) or not authenticated_owner_id.strip():
        raise ValueError("INVALID_AUTHENTICATED_OWNER")
    if not isinstance(now_ms, int) or isinstance(now_ms, bool) or now_ms < 0:
        raise ValueError("INVALID_TIMESTAMP")
    if not isinstance(server_secret, bytes) or len(server_secret) < 32:
        raise ValueError("INVALID_SERVER_SECRET")
    purchase = verify_and_map_subscription(
        purchase_token=purchase_token, access_token=access_token,
        owner_id=authenticated_owner_id, product_id=product_id,
        server_secret=server_secret, opener=opener,
    )
    digest = token_digest(purchase_token)
    if not entitlement_allowed(purchase, owner_id=authenticated_owner_id,
                               product_id=product_id, token_sha256=digest,
                               now_ms=now_ms):
        return False
    bind_or_verify_owner(db, purchase_token=purchase_token,
                         authenticated_owner_id=authenticated_owner_id, now_ms=now_ms)
    return True
