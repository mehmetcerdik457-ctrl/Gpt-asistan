"""OpenAI Standard Webhooks signature verification for the existing KRAL gateway.

The verifier authenticates the exact raw request bytes before JSON parsing. It
uses the Standard Webhooks v1 HMAC format and a five-minute timestamp window.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time

MAX_WEBHOOK_BODY = 65536
DEFAULT_TOLERANCE_SECONDS = 300
_ID = re.compile(r"[A-Za-z0-9_=-]{1,200}\Z")
_TYPE = re.compile(r"[A-Za-z0-9_.-]{1,120}\Z")


class WebhookError(ValueError):
    def __init__(self, code: str, status: int = 400):
        self.code = code
        self.status = status
        super().__init__(code)


def _header(headers, name: str, maximum: int) -> str:
    value = headers.get(name)
    if not isinstance(value, str):
        raise WebhookError("WEBHOOK_HEADERS_INVALID")
    value = value.strip()
    if not value or len(value) > maximum or not value.isascii():
        raise WebhookError("WEBHOOK_HEADERS_INVALID")
    return value


def verify_and_parse(raw_body: bytes, headers, secret: str | None = None, *,
                     now: int | None = None,
                     tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS) -> tuple[dict, str]:
    """Verify OpenAI webhook signature, then parse and validate its event.

    Returns (event, authenticated webhook-id). No network or side effects.
    """
    if not isinstance(raw_body, bytes) or not 0 < len(raw_body) <= MAX_WEBHOOK_BODY:
        raise WebhookError("WEBHOOK_BODY_INVALID", 413)
    if secret is None:
        import os
        secret = os.getenv("OPENAI_WEBHOOK_SECRET", "")
    if not isinstance(secret, str) or not secret.strip():
        raise WebhookError("WEBHOOK_SECRET_NOT_CONFIGURED", 503)
    secret = secret.strip()
    if secret.startswith("whsec_"):
        encoded = secret[6:]
        try:
            key = base64.b64decode(encoded + "=" * (-len(encoded) % 4), validate=True)
        except (ValueError, TypeError):
            raise WebhookError("WEBHOOK_SECRET_INVALID", 503) from None
    else:
        # Permit raw secrets for Standard Webhooks-compatible test/deployment setups.
        key = secret.encode("utf-8")
    if not key or len(key) > 512:
        raise WebhookError("WEBHOOK_SECRET_INVALID", 503)

    webhook_id = _header(headers, "webhook-id", 200)
    timestamp_text = _header(headers, "webhook-timestamp", 16)
    signature_header = _header(headers, "webhook-signature", 2048)
    if not _ID.fullmatch(webhook_id) or not timestamp_text.isdigit():
        raise WebhookError("WEBHOOK_HEADERS_INVALID")
    timestamp = int(timestamp_text)
    current = int(time.time()) if now is None else int(now)
    if abs(current - timestamp) > tolerance_seconds:
        raise WebhookError("WEBHOOK_TIMESTAMP_OUT_OF_RANGE")

    signed = webhook_id.encode("ascii") + b"." + timestamp_text.encode("ascii") + b"." + raw_body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode("ascii")
    valid = False
    for candidate in signature_header.split():
        version, separator, signature = candidate.partition(",")
        if separator and version == "v1":
            valid = hmac.compare_digest(signature, expected) or valid
    if not valid:
        raise WebhookError("WEBHOOK_SIGNATURE_INVALID")

    try:
        event = json.loads(raw_body)
    except (ValueError, UnicodeError):
        raise WebhookError("WEBHOOK_JSON_INVALID") from None
    if (not isinstance(event, dict) or event.get("object") != "event"
            or not isinstance(event.get("id"), str) or not _ID.fullmatch(event["id"])
            or not isinstance(event.get("type"), str) or not _TYPE.fullmatch(event["type"])
            or not isinstance(event.get("data"), dict)):
        raise WebhookError("WEBHOOK_EVENT_INVALID")
    return event, webhook_id
