"""Owner-authenticated KRAL/ORBA Google Play server boundary (candidate).

Unlike a client-supplied owner_id, identities accepted by this boundary MUST
come from the existing dual-P256 authenticated owner gateway. Credentials,
secret and DB connection are injected by a trusted server installer, not
request bodies. There is deliberately NO default live OAuth implementation.
"""
from __future__ import annotations

import re
import time
from contextlib import closing

from server.play_account_id import obfuscated_play_account_id
from server.play_acknowledgement_service import acknowledge_then_verify_subscription
from server.play_entitlement_gate import PRODUCT_RE


class PlayBoundaryError(RuntimeError):
    """Fixed non-sensitive error; no token or OAuth credentials in responses."""


class PlayGatewayBoundary:
    def __init__(self, *, server_secret: bytes, allowed_products,
                 oauth_supplier, db_factory, opener=None, clock_ms=None,
                 snapshot_recorder=None):
        if not isinstance(server_secret, bytes) or len(server_secret) < 32:
            raise ValueError("ORBA_SERVER_SECRET_NOT_PROVISIONED")
        if (not isinstance(allowed_products, (set, frozenset))
                or not allowed_products or
                any(not isinstance(x, str) or not PRODUCT_RE.fullmatch(x)
                    for x in allowed_products)):
            raise ValueError("ORBA_ALLOWLIST_NOT_PROVISIONED")
        if not callable(oauth_supplier) or not callable(db_factory):
            raise ValueError("ORBA_PROVIDER_OR_STORE_NOT_PROVISIONED")
        self._secret = server_secret
        self._products = frozenset(allowed_products)
        self._oauth = oauth_supplier
        self._db_factory = db_factory
        self._opener = opener
        if snapshot_recorder is not None and not callable(snapshot_recorder):
            raise ValueError("SNAPSHOT_RECORDER_INVALID")
        self._snapshot_recorder = snapshot_recorder
        self._clock_ms = clock_ms if clock_ms is not None else lambda: int(time.time() * 1000)
        if not callable(self._clock_ms):
            raise ValueError("ORBA_CLOCK_NOT_PROVISIONED")

    @staticmethod
    def _owner(owner: str) -> str:
        if (not isinstance(owner, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", owner)):
            raise PlayBoundaryError("AUTHENTICATED_OWNER_REQUIRED")
        return owner

    def account_id(self, *, authenticated_owner_id: str) -> str:
        owner = self._owner(authenticated_owner_id)
        return obfuscated_play_account_id(authenticated_owner_id=owner,
                                           server_secret=self._secret)

    def verify(self, *, authenticated_owner_id: str, product_id: str,
               purchase_token: str) -> bool:
        owner = self._owner(authenticated_owner_id)
        if (not isinstance(product_id, str) or
                product_id not in self._products):
            raise PlayBoundaryError("PRODUCT_NOT_ALLOWED")
        if not isinstance(purchase_token, str) or not 1 <= len(purchase_token) <= 4096:
            raise PlayBoundaryError("INVALID_PURCHASE_TOKEN")
        if any(c.isspace() or ord(c) < 33 for c in purchase_token):
            raise PlayBoundaryError("INVALID_PURCHASE_TOKEN")
        now_ms = self._clock_ms()
        if not isinstance(now_ms, int) or isinstance(now_ms, bool) or now_ms < 0:
            raise PlayBoundaryError("SERVER_CLOCK_INVALID")
        try:
            access_token = self._oauth()
        except Exception:
            raise PlayBoundaryError("PROVIDER_CREDENTIAL_UNAVAILABLE") from None
        if (not isinstance(access_token, str) or not access_token
                or len(access_token) > 8192
                or any(c.isspace() or ord(c) < 33 for c in access_token)):
            raise PlayBoundaryError("PROVIDER_CREDENTIAL_UNAVAILABLE")
        # db_factory MUST provide an externally migrated, private durable DB.
        # Never auto-create schema on the public request path.
        try:
            with closing(self._db_factory()) as db:
                with db:
                    return bool(acknowledge_then_verify_subscription(
                        db=db, purchase_token=purchase_token,
                        access_token=access_token,
                        authenticated_owner_id=owner, product_id=product_id,
                        server_secret=self._secret, now_ms=now_ms,
                        opener=self._opener,
                        snapshot_recorder=self._snapshot_recorder,
                    ))
        except PlayBoundaryError:
            raise
        except Exception:
            # Never expose provider payloads, purchase tokens or raw errors.
            # Caller maps this to 503; DB/provider failure grants no rights.
            raise PlayBoundaryError("PLAY_VERIFICATION_UNAVAILABLE") from None
