"""Fail-closed orchestration for Play verification, entitlement and ownership.

Only invoke after trusted session authentication. No production HTTP route,
credential issuance, BillingClient, or live purchases are implemented here.
"""
from server.play_entitlement_gate import entitlement_allowed, token_digest
from server.play_subscription_mapper import verify_and_map_subscription
from server.play_owner_binding import bind_or_verify_owner


def verify_play_entitlement(*, db, purchase_token: str, access_token: str,
                            authenticated_owner_id: str, product_id: str,
                            server_secret: bytes, now_ms: int, opener=None,
                            owner_binder=None, clock_ms=None) -> bool:
    """No owner binding is written unless provider, account and entitlement pass."""
    if not isinstance(authenticated_owner_id, str) or not authenticated_owner_id.strip():
        raise ValueError("INVALID_AUTHENTICATED_OWNER")
    if not isinstance(now_ms, int) or isinstance(now_ms, bool) or now_ms < 0:
        raise ValueError("INVALID_TIMESTAMP")
    if not isinstance(server_secret, bytes) or len(server_secret) < 32:
        raise ValueError("INVALID_SERVER_SECRET")
    if owner_binder is not None and not callable(owner_binder):
        raise ValueError("OWNER_BINDER_INVALID")
    if clock_ms is not None and not callable(clock_ms):
        raise ValueError("SERVER_CLOCK_INVALID")
    purchase = verify_and_map_subscription(
        purchase_token=purchase_token, access_token=access_token,
        owner_id=authenticated_owner_id, product_id=product_id,
        server_secret=server_secret, opener=opener,
    )
    decision_ms = clock_ms() if clock_ms is not None else now_ms
    if (type(decision_ms) is not int or not now_ms <= decision_ms <= 4102444800000):
        raise ValueError("SERVER_CLOCK_INVALID")
    digest = token_digest(purchase_token)
    if not entitlement_allowed(purchase, owner_id=authenticated_owner_id,
                               product_id=product_id, token_sha256=digest,
                               now_ms=decision_ms):
        return False
    binder = owner_binder if owner_binder is not None else bind_or_verify_owner
    binder(db, purchase_token=purchase_token,
           authenticated_owner_id=authenticated_owner_id, now_ms=decision_ms)
    final_ms = clock_ms() if clock_ms is not None else now_ms
    if type(final_ms) is not int or not decision_ms <= final_ms <= 4102444800000:
        raise ValueError("SERVER_CLOCK_INVALID")
    if not entitlement_allowed(purchase, owner_id=authenticated_owner_id,
                               product_id=product_id, token_sha256=digest,
                               now_ms=final_ms):
        raise ValueError("PLAY_VERIFICATION_EXPIRED")
    return True
