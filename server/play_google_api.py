"""Read-only Google Play subscriptionsv2 lookup. Server-side only.

The OAuth access token must be issued by a trusted server credential provider
with Android Publisher scope. This module never acknowledges or purchases.
"""
from __future__ import annotations
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request

API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
PACKAGE = "com.example.gptasistan.genesis"
TOKEN_RE = re.compile(r"^[A-Za-z0-9._~%-]{1,8192}$")
MAX_RESPONSE = 262144
MAX_JSON_DEPTH = 32


class PlayVerificationError(RuntimeError):
    pass


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        # OAuth Authorization headers must never follow a redirect, including
        # a redirect to another Google endpoint or an attacker-selected host.
        return None


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate provider JSON member")
        value[key] = item
    return value


def _invalid_constant(_value):
    raise ValueError("non-finite provider JSON number")


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("non-finite provider JSON number")
    return result


def _provider_json(raw):
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                      parse_constant=_invalid_constant, parse_float=_finite_float)
    pending = [(data, 1)]
    while pending:
        item, depth = pending.pop()
        if depth > MAX_JSON_DEPTH:
            raise ValueError("provider JSON nesting bound")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    return data


def get_subscription_v2(purchase_token: str, access_token: str, *, opener=None) -> dict:
    """Query purchases.subscriptionsv2.get, failing closed on all errors.

    The caller must independently authenticate the account, obtain an OAuth
    token server-side, bind the purchase to an account and validate lineItems.
    Do not log raw tokens, authorization headers, or full provider payloads.
    """
    if not isinstance(purchase_token, str) or not TOKEN_RE.fullmatch(purchase_token):
        raise PlayVerificationError("INVALID_PURCHASE_TOKEN")
    if (not isinstance(access_token, str) or not 1 <= len(access_token) <= 8192 or
            not access_token.isascii() or
            any(not 33 <= ord(char) < 127 or char.isspace() for char in access_token)):
        raise PlayVerificationError("INVALID_SERVER_CREDENTIAL")
    encoded_package = urllib.parse.quote(PACKAGE, safe="")
    encoded_token = urllib.parse.quote(purchase_token, safe="")
    url = f"{API}/{encoded_package}/purchases/subscriptionsv2/tokens/{encoded_token}"
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + access_token,
        "Accept": "application/json",
    }, method="GET")
    open_request = opener or urllib.request.build_opener(_RejectRedirects()).open
    try:
        with open_request(request, timeout=8) as response:
            status = getattr(response, "status", None)
            if type(status) is not int or status != 200:
                raise PlayVerificationError("GOOGLE_PLAY_HTTP_ERROR")
            raw = response.read(MAX_RESPONSE + 1)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise PlayVerificationError("GOOGLE_PLAY_UNAVAILABLE") from None
    if not isinstance(raw, bytes):
        raise PlayVerificationError("GOOGLE_PLAY_INVALID_RESPONSE")
    if len(raw) > MAX_RESPONSE:
        raise PlayVerificationError("GOOGLE_PLAY_RESPONSE_TOO_LARGE")
    try:
        data = _provider_json(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise PlayVerificationError("GOOGLE_PLAY_INVALID_RESPONSE") from None
    if not isinstance(data, dict) or not isinstance(data.get("subscriptionState"), str) or not isinstance(data.get("lineItems"), list):
        raise PlayVerificationError("GOOGLE_PLAY_INVALID_RESPONSE")
    if not data["lineItems"] or any(not isinstance(item, dict) or not isinstance(item.get("productId"), str) or not item["productId"] for item in data["lineItems"]):
        raise PlayVerificationError("GOOGLE_PLAY_INVALID_LINE_ITEMS")
    return data
