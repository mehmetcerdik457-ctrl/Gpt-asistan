"""Strict Google Play subscriptionsv2 response-to-decision adapter.

Call ONLY with a response obtained directly by the trusted server-side
get_subscription_v2 client, and an independently authenticated owner binding.
No client-supplied dict may be passed to this function as trusted evidence.
"""
from datetime import datetime, timezone
from server.play_entitlement_gate import VerifiedPlayPurchase, PACKAGE, token_digest


class PlayMappingError(ValueError):
    pass


def _expiry_ms(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise PlayMappingError("INVALID_EXPIRY")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PlayMappingError("INVALID_EXPIRY") from exc
    if dt.tzinfo is None or dt.year < 2020:
        raise PlayMappingError("INVALID_EXPIRY")
    return int(dt.timestamp() * 1000)


def map_verified_subscription(data: dict, *, purchase_token: str, owner_id: str,
                              product_id: str) -> VerifiedPlayPurchase:
    """Map trusted provider response. Authentication and ownership are external."""
    if not isinstance(data, dict) or not isinstance(owner_id, str) or not owner_id:
        raise PlayMappingError("INVALID_OWNER_OR_RESPONSE")
    if not isinstance(product_id, str) or not product_id:
        raise PlayMappingError("INVALID_PRODUCT")
    if data.get("acknowledgementState") not in (
        "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED",
        "ACKNOWLEDGEMENT_STATE_PENDING",
    ):
        raise PlayMappingError("INVALID_ACKNOWLEDGEMENT")
    items = data.get("lineItems")
    if not isinstance(items, list) or not items:
        raise PlayMappingError("MISSING_LINE_ITEMS")
    matches = [item for item in items if isinstance(item, dict) and item.get("productId") == product_id]
    if len(matches) != 1:
        raise PlayMappingError("PRODUCT_NOT_UNIQUE")
    expiry = _expiry_ms(matches[0].get("expiryTime"))
    state = data.get("subscriptionState")
    if not isinstance(state, str):
        raise PlayMappingError("INVALID_STATE")
    return VerifiedPlayPurchase(
        package_name=PACKAGE,
        product_id=product_id,
        purchase_token_sha256=token_digest(purchase_token),
        owner_id=owner_id,
        expires_at_ms=expiry,
        subscription_state=state,
        acknowledged=data["acknowledgementState"] == "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED",
        verified_by_google_api=True,
    )
