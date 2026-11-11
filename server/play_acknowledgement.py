"""Offline-testable Google Play subscription ACK adapter; never trusts the client.

Only an authenticated backend can provide the Google Publisher OAuth token.
This module issues a provider acknowledgement request, NOT a payment or grant.
"""
from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request

from server.play_entitlement_gate import PACKAGE, PRODUCT_RE
from server.play_google_api import API, TOKEN_RE


class PlayAcknowledgementError(RuntimeError):
    """Redacted provider failure: contains neither purchase token nor OAuth key."""


def acknowledge_subscription(*, purchase_token: str, product_id: str,
                             access_token: str, opener=None) -> None:
    """Acknowledge a verified initial subscription through Android Publisher.

    The caller MUST first validate owner/account, ACTIVE state, product and
    expiry using a fresh trusted subscriptionsv2 GET. It MUST make a second
    GET after this call and withhold entitlement until Play confirms ACKNOWLEDGED.
    """
    if not isinstance(purchase_token, str) or not TOKEN_RE.fullmatch(purchase_token):
        raise PlayAcknowledgementError("INVALID_PURCHASE_TOKEN")
    if not isinstance(product_id, str) or not PRODUCT_RE.fullmatch(product_id):
        raise PlayAcknowledgementError("INVALID_PRODUCT")
    if (not isinstance(access_token, str) or not access_token or
            len(access_token) > 8192 or any(char.isspace() or ord(char) < 32 for char in access_token)):
        raise PlayAcknowledgementError("INVALID_SERVER_CREDENTIAL")
    package = urllib.parse.quote(PACKAGE, safe="")
    product = urllib.parse.quote(product_id, safe="")
    token = urllib.parse.quote(purchase_token, safe="")
    url = (f"{API}/{package}/purchases/subscriptions/{product}"
           f"/tokens/{token}:acknowledge")
    request = urllib.request.Request(
        url,
        data=b"{}",
        headers={
            "Authorization": "Bearer " + access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    open_request = opener or urllib.request.urlopen
    try:
        with open_request(request, timeout=8) as response:
            if getattr(response, "status", 200) not in (200, 204):
                raise PlayAcknowledgementError("GOOGLE_PLAY_ACK_REJECTED")
            # ACK returns empty body; do not log or store provider response.
            if len(response.read(4097)) > 4096:
                raise PlayAcknowledgementError("GOOGLE_PLAY_ACK_RESPONSE_TOO_LARGE")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PlayAcknowledgementError("GOOGLE_PLAY_ACK_UNAVAILABLE") from exc
