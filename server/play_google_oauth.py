"""Opt-in server-only Google Play Publisher OAuth access-token supplier.

Never publish tokens or service account keys. Does NOT auto-enable any Play
endpoint; the trusted deployer must inject this callable deliberately.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hmac
import os
import re
import threading
import time

ANDROIDPUBLISHER_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
SERVICE_ACCOUNT_PATTERN = re.compile(
    r"^[A-Za-z0-9_.-]{1,128}@[A-Za-z0-9_.-]+\.iam\.gserviceaccount\.com$"
)


class PublisherOAuthUnavailable(RuntimeError):
    """Generic fixed error; never includes credential identity or access token."""


def _default_loader(*, scopes):
    import google.auth
    return google.auth.default(scopes=scopes)


def _default_request():
    from google.auth.transport.requests import Request
    return Request()


class PlayPublisherOAuth:
    """Cache short-lived ADC token for one explicitly configured service account.

    The ambient credential must identify the exact Google service-account
    principal. End-user OAuth credentials and unidentified workload identities
    fail closed. Workload Identity Federation via service-account impersonation
    may be used only when it presents the expected service_account_email.
    """
    def __init__(self, *, service_account_email, credential_loader=None,
                 request_factory=None, now=None, enabled=None):
        if (not isinstance(service_account_email, str) or
                not SERVICE_ACCOUNT_PATTERN.fullmatch(service_account_email)):
            raise ValueError("PUBLISHER_SERVICE_ACCOUNT_NOT_CONFIGURED")
        self._email = service_account_email
        self._loader = credential_loader or _default_loader
        self._request_factory = request_factory or _default_request
        self._now = now or time.time
        self._enabled = enabled if enabled is not None else (
            lambda: os.getenv("ORBA_PLAY_OAUTH_ENABLED") == "YES")
        if not all(callable(x) for x in
                   (self._loader, self._request_factory, self._now, self._enabled)):
            raise ValueError("PUBLISHER_PROVIDER_INVALID")
        self._lock = threading.RLock()
        self._credentials = None

    def __call__(self):
        # Feature flag check occurs on EVERY call, even when token is cached.
        if self._enabled() is not True:
            raise PublisherOAuthUnavailable("PUBLISHER_OAUTH_DISABLED")
        with self._lock:
            try:
                if self._credentials is None:
                    credentials, _project = self._loader(
                        scopes=[ANDROIDPUBLISHER_SCOPE])
                    identity = getattr(credentials, "service_account_email", None)
                    if (not isinstance(identity, str) or
                            not hmac.compare_digest(identity, self._email)):
                        raise ValueError()
                    check_scopes = getattr(credentials, "has_scopes", None)
                    if not callable(check_scopes) or not check_scopes(
                            [ANDROIDPUBLISHER_SCOPE]):
                        raise ValueError()
                    self._credentials = credentials

                now = float(self._now())
                if not 0 < now < 4102444800:
                    raise ValueError()
                exp = getattr(self._credentials, "expiry", None)
                if isinstance(exp, datetime):
                    expiry = exp.replace(tzinfo=timezone.utc) if exp.tzinfo is None else exp
                    expiry_secs = expiry.timestamp()
                else:
                    expiry_secs = 0.0
                token = getattr(self._credentials, "token", None)
                if not self._valid_token(token) or expiry_secs <= now + 60:
                    self._credentials.refresh(self._request_factory())
                    token = getattr(self._credentials, "token", None)
                    exp = getattr(self._credentials, "expiry", None)
                    if not isinstance(exp, datetime):
                        raise ValueError()
                    expiry = exp.replace(tzinfo=timezone.utc) if exp.tzinfo is None else exp
                    expiry_secs = expiry.timestamp()
                if not self._valid_token(token) or expiry_secs <= now + 60:
                    raise ValueError()
                return token
            except PublisherOAuthUnavailable:
                raise
            except Exception:
                # Treat all local/Google auth failure as unavailable without
                # exposing refresh tokens, account IDs, paths, or provider data.
                raise PublisherOAuthUnavailable("PUBLISHER_OAUTH_UNAVAILABLE") from None

    @staticmethod
    def _valid_token(token):
        return (isinstance(token, str) and 1 <= len(token) <= 8192 and
                token.isascii() and all(32 < ord(c) < 127 and not c.isspace()
                                        for c in token))
