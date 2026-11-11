"""Read-only Google Play subscriptionsv2 lookup. Server-side only.

The OAuth access token must be issued by a trusted server credential provider
with Android Publisher scope. This module never acknowledges or purchases.
"""
from __future__ import annotations
import json
import re
import urllib.error
import urllib.parse
import urllib.request

API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
PACKAGE = "com.example.gptasistan.genesis"
TOKEN_RE = re.compile(r"^[A-Za-z0-9._~%-]{1,8192}$")


class PlayVerificationError(RuntimeError):
    pass


def get_subscription_v2(purchase_token: str, access_token: str, *, opener=None) -> dict:
    """Query purchases.subscriptionsv2.get, failing closed on all errors.

    The caller must independently authenticate the account, obtain an OAuth
    token server-side, bind the purchase to an account and validate lineItems.
    Do not log raw tokens, authorization headers, or full provider payloads.
    """
    if not isinstance(purchase_token, str) or not TOKEN_RE.fullmatch(purchase_token):
        raise PlayVerificationError("INVALID_PURCHASE_TOKEN")
    if not isinstance(access_token, str) or not access_token or "\r" in access_token or "\n" in access_token:
        raise PlayVerificationError("INVALID_SERVER_CREDENTIAL")
    encoded_package = urllib.parse.quote(PACKAGE, safe="")
    encoded_token = urllib.parse.quote(purchase_token, safe="")
    url = f"{API}/{encoded_package}/purchases/subscriptionsv2/tokens/{encoded_token}"
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + access_token,
        "Accept": "application/json",
    }, method="GET")
    open_request = opener or urllib.request.urlopen
    try:
        with open_request(request, timeout=8) as response:
            if getattr(response, "status", 200) != 200:
                raise PlayVerificationError("GOOGLE_PLAY_HTTP_ERROR")
            raw = response.read(262145)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PlayVerificationError("GOOGLE_PLAY_UNAVAILABLE") from exc
    if len(raw) > 262144:
        raise PlayVerificationError("GOOGLE_PLAY_RESPONSE_TOO_LARGE")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise PlayVerificationError("GOOGLE_PLAY_INVALID_RESPONSE") from exc
    if not isinstance(data, dict) or not isinstance(data.get("subscriptionState"), str) or not isinstance(data.get("lineItems"), list):
        raise PlayVerificationError("GOOGLE_PLAY_INVALID_RESPONSE")
    if not data["lineItems"] or any(not isinstance(item, dict) or not isinstance(item.get("productId"), str) or not item["productId"] for item in data["lineItems"]):
        raise PlayVerificationError("GOOGLE_PLAY_INVALID_LINE_ITEMS")
    return data
