"""Deterministic privacy-preserving Play account identifier.

Server secret is never embedded in APK. The Android BillingFlowParams account
identifier must be obtained through an authenticated, rate-limited backend.
"""
import hashlib
import hmac


def obfuscated_play_account_id(*, authenticated_owner_id: str, server_secret: bytes) -> str:
    if not isinstance(authenticated_owner_id, str) or not authenticated_owner_id.strip():
        raise ValueError("INVALID_AUTHENTICATED_OWNER")
    if len(authenticated_owner_id.encode("utf-8")) > 256:
        raise ValueError("OWNER_ID_TOO_LONG")
    if not isinstance(server_secret, bytes) or len(server_secret) < 32:
        raise ValueError("INVALID_SERVER_SECRET")
    # Domain separation prevents reuse of the digest for unrelated purposes.
    message = b"orba-play-obfuscated-account-v1\x00" + authenticated_owner_id.encode("utf-8")
    return hmac.new(server_secret, message, hashlib.sha256).hexdigest()
