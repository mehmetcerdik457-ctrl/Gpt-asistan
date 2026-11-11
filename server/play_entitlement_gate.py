"""Fail-closed Google Play entitlement decision core; NOT a Play API client.

Only a trusted server-side Google Play Developer API adapter may construct a
VerifiedPlayPurchase. Never accept this object from a client request body.
"""
from dataclasses import dataclass
import hashlib
import hmac
import re

PACKAGE = "com.example.gptasistan.genesis"
PRODUCT_RE = re.compile(r"^[A-Za-z0-9_.]{1,100}$")


@dataclass(frozen=True)
class VerifiedPlayPurchase:
    package_name: str
    product_id: str
    purchase_token_sha256: str
    owner_id: str
    expires_at_ms: int
    subscription_state: str
    acknowledged: bool
    verified_by_google_api: bool


def token_digest(token: str) -> str:
    if not isinstance(token, str) or not token or len(token) > 8192:
        raise ValueError("INVALID_PURCHASE_TOKEN")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def entitlement_allowed(purchase: VerifiedPlayPurchase, *, owner_id: str,
                        product_id: str, token_sha256: str, now_ms: int) -> bool:
    """Pure decision; caller MUST independently authenticate owner_id.

    Acknowledgement is required for this conservative initial gate. The
    integration must acknowledge verified purchases promptly through Play API.
    """
    if not isinstance(purchase, VerifiedPlayPurchase):
        return False
    if not isinstance(owner_id, str) or not owner_id or not isinstance(product_id, str):
        return False
    if not PRODUCT_RE.fullmatch(product_id) or not isinstance(token_sha256, str):
        return False
    if not re.fullmatch(r"[a-f0-9]{64}", token_sha256):
        return False
    if not isinstance(now_ms, int) or isinstance(now_ms, bool) or now_ms < 0:
        return False
    if not purchase.verified_by_google_api or not purchase.acknowledged:
        return False
    if purchase.package_name != PACKAGE or purchase.product_id != product_id:
        return False
    if purchase.owner_id != owner_id or not hmac.compare_digest(purchase.purchase_token_sha256, token_sha256):
        return False
    if not isinstance(purchase.expires_at_ms, int) or isinstance(purchase.expires_at_ms, bool):
        return False
    if purchase.expires_at_ms <= now_ms:
        return False
    return purchase.subscription_state == "SUBSCRIPTION_STATE_ACTIVE"
