"""Fail-closed Google Play purchase verification primitives.

This module does not move money or modify Play Console/bank settings.
The caller must authenticate Pub/Sub push JWTs before calling
`parse_rtdn_payload`, and must inject an authenticated Android Publisher API
client. Raw purchase tokens are never included in returned records or logs.
"""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping


class PurchaseVerificationError(ValueError):
    """Raised when an RTDN message or purchase cannot be verified."""


@dataclass(frozen=True)
class VerifiedPurchase:
    package_name: str
    product_id: str
    purchase_token_sha256: str
    purchase_state: str
    acknowledgement_state: str | None
    order_id: str | None
    start_time: str | None
    expiry_time: str | None
    auto_renewing: bool | None
    source: str


def parse_rtdn_payload(envelope: Mapping[str, Any], *,
                       expected_package: str) -> dict[str, Any]:
    """Decode a Pub/Sub push envelope after its OIDC JWT was verified upstream.

    Required caller-side checks: verify Google-signed OIDC token, exact audience,
    expected service-account email and email_verified=True. This function alone
    does NOT authenticate the HTTP sender.
    """
    message = envelope.get("message")
    if not isinstance(message, Mapping):
        raise PurchaseVerificationError("RTDN_MESSAGE_MISSING")
    encoded = message.get("data")
    if not isinstance(encoded, str) or not encoded:
        raise PurchaseVerificationError("RTDN_DATA_MISSING")
    try:
        raw = base64.b64decode(encoded, validate=True)
        event = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise PurchaseVerificationError("RTDN_DATA_INVALID") from None

    package_name = event.get("packageName")
    if package_name != expected_package:
        raise PurchaseVerificationError("RTDN_PACKAGE_MISMATCH")
    if not isinstance(event.get("eventTimeMillis"), (int, str)):
        raise PurchaseVerificationError("RTDN_EVENT_TIME_MISSING")

    notice = event.get("subscriptionNotification") or event.get("oneTimeProductNotification")
    if not isinstance(notice, Mapping):
        # Test notifications are acknowledged but never treated as purchases.
        if "testNotification" in event:
            return {"kind": "test", "package_name": package_name,
                    "event_time_millis": str(event["eventTimeMillis"]),
                    "message_id": str(message.get("messageId", ""))}
        raise PurchaseVerificationError("RTDN_PURCHASE_NOTICE_MISSING")

    token = notice.get("purchaseToken")
    product_id = notice.get("subscriptionId") or notice.get("sku")
    if not isinstance(token, str) or not token or not isinstance(product_id, str) or not product_id:
        raise PurchaseVerificationError("RTDN_PURCHASE_FIELDS_MISSING")
    return {
        "kind": "purchase_notice",
        "package_name": package_name,
        "product_id": product_id,
        "purchase_token": token,
        "purchase_token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        "notification_type": notice.get("notificationType"),
        "event_time_millis": str(event["eventTimeMillis"]),
        "message_id": str(message.get("messageId", "")),
    }


def verify_subscription(*, publisher_api: Any, package_name: str,
                        product_id: str, purchase_token: str) -> VerifiedPurchase:
    """Verify a subscription using Android Publisher API subscriptionsv2.get.

    publisher_api must be an authenticated googleapiclient Android Publisher
    v3 client with the required read-only entitlement. No token is persisted.
    """
    if not all(isinstance(v, str) and v for v in
               (package_name, product_id, purchase_token)):
        raise PurchaseVerificationError("PURCHASE_INPUT_MISSING")
    try:
        response = (publisher_api.purchases().subscriptionsv2()
                    .get(packageName=package_name, token=purchase_token)
                    .execute())
    except Exception as exc:
        # Avoid leaking tokens, credentials or provider response bodies.
        raise PurchaseVerificationError(
            "PLAY_API_VERIFICATION_FAILED:" + type(exc).__name__) from None

    line_items = response.get("lineItems") or []
    item = next((x for x in line_items if x.get("productId") == product_id), None)
    if item is None:
        raise PurchaseVerificationError("PLAY_PRODUCT_NOT_IN_PURCHASE")
    state = response.get("subscriptionState")
    if not isinstance(state, str) or not state:
        raise PurchaseVerificationError("PLAY_SUBSCRIPTION_STATE_MISSING")

    auto_renew = item.get("autoRenewingPlan")
    auto_renewing = (bool(auto_renew.get("autoRenewEnabled"))
                     if isinstance(auto_renew, Mapping) else None)
    external_ids = response.get("externalAccountIdentifiers") or {}
    # external account identifiers are deliberately not returned or logged.
    del external_ids

    return VerifiedPurchase(
        package_name=package_name,
        product_id=product_id,
        purchase_token_sha256=hashlib.sha256(purchase_token.encode("utf-8")).hexdigest(),
        purchase_state=state,
        acknowledgement_state=response.get("acknowledgementState"),
        order_id=response.get("latestOrderId"),
        start_time=item.get("startTime"),
        expiry_time=item.get("expiryTime"),
        auto_renewing=auto_renewing,
        source="androidpublisher.subscriptionsv2.get",
    )


def public_record(purchase: VerifiedPurchase) -> dict[str, Any]:
    """Return a safe report row. Never contains the raw purchase token."""
    return asdict(purchase)


def acknowledge_delivery(*, publisher_api: Any, package_name: str,
                         product_id: str, purchase_token: str) -> None:
    """Acknowledge a subscription only after business rules explicitly allow it.

    This operation changes Play purchase state; therefore this helper is
    intentionally not called by RTDN parsing or verification automatically.
    """
    if not all(isinstance(v, str) and v for v in
               (package_name, product_id, purchase_token)):
        raise PurchaseVerificationError("ACK_INPUT_MISSING")
    publisher_api.purchases().subscriptions().acknowledge(
        packageName=package_name, subscriptionId=product_id,
        token=purchase_token, body={}
    ).execute()
