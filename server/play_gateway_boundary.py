"""Owner-authenticated KRAL/ORBA Google Play server boundary (candidate).

Unlike a client-supplied owner_id, identities accepted by this boundary MUST
come from the existing dual-P256 authenticated owner gateway. Credentials,
secret and DB connection are injected by a trusted server installer, not
request bodies. There is deliberately NO default live OAuth implementation.
"""
from __future__ import annotations

import re
import time

from server.play_account_id import obfuscated_play_account_id
from server.play_acknowledgement_service import acknowledge_then_verify_subscription
from server.play_entitlement_gate import PRODUCT_RE, token_digest, entitlement_allowed
from server.play_purchase_store import SQLitePlayStore


class PlayBoundaryError(RuntimeError):
    """Fixed non-sensitive error; no token or OAuth credentials in responses."""


class PlayGatewayBoundary:
    def __init__(self, *, server_secret: bytes, allowed_products,
                 oauth_supplier, db_factory=None, opener=None, clock_ms=None,
                 snapshot_recorder=None, store=None):
        if not isinstance(server_secret, bytes) or len(server_secret) < 32:
            raise ValueError("ORBA_SERVER_SECRET_NOT_PROVISIONED")
        if (not isinstance(allowed_products, (set, frozenset))
                or not allowed_products or
                any(not isinstance(x, str) or not PRODUCT_RE.fullmatch(x)
                    for x in allowed_products)):
            raise ValueError("ORBA_ALLOWLIST_NOT_PROVISIONED")
        if (not callable(oauth_supplier) or
                (store is None and not callable(db_factory)) or
                (store is not None and (
                    db_factory is not None or snapshot_recorder is not None or
                    not callable(getattr(store, "verification", None))))):
            raise ValueError("ORBA_PROVIDER_OR_STORE_NOT_PROVISIONED")
        self._secret = server_secret
        self._products = frozenset(allowed_products)
        self._oauth = oauth_supplier
        self._db_factory = db_factory
        self._store = store
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

    def account_configuration(self, *, authenticated_owner_id: str) -> dict:
        """Return only authenticated checkout input, never an entitlement.

        Google Play remains the source of eligible offers and displayed prices;
        the server allowlist prevents the Android UI inventing product IDs.
        """
        return {
            "obfuscated_account_id": self.account_id(
                authenticated_owner_id=authenticated_owner_id),
            "products": sorted(self._products),
        }

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
            store = self._store if self._store is not None else SQLitePlayStore(self._db_factory)
            with store.verification(token_sha256=token_digest(purchase_token),
                                    authenticated_owner_id=owner) as transaction:
                now_ms = transaction.observation_time_ms(self._clock_ms)
                authorization_deadline = None

                def observe_verified(purchase):
                    nonlocal authorization_deadline
                    started = time.monotonic()
                    checked = transaction.observation_time_ms(self._clock_ms)
                    if (type(checked) is not int or checked < now_ms or
                            not entitlement_allowed(
                                purchase, owner_id=owner, product_id=product_id,
                                token_sha256=token_digest(purchase_token), now_ms=checked)):
                        raise ValueError("PLAY_VERIFICATION_EXPIRED")
                    # Conservative monotonic deadline also covers a slow commit
                    # after the last database-clock check, without opening a
                    # new connection or trusting a different worker wall clock.
                    authorization_deadline = started + (purchase.expires_at_ms - checked) / 1000

                recorder = (transaction.record_snapshot if self._store is not None
                            else self._snapshot_recorder)
                allowed = bool(acknowledge_then_verify_subscription(
                        db=transaction.connection, purchase_token=purchase_token,
                        access_token=access_token,
                        authenticated_owner_id=owner, product_id=product_id,
                        server_secret=self._secret, now_ms=now_ms,
                        opener=self._opener,
                        snapshot_recorder=recorder,
                        owner_binder=transaction.bind_verified_owner,
                        clock_ms=lambda: transaction.observation_time_ms(self._clock_ms),
                        verified_observer=observe_verified,
                    ))
            # Only return a grant after the ownership/snapshot commit succeeds.
            return allowed and authorization_deadline is not None and time.monotonic() < authorization_deadline
        except PlayBoundaryError:
            raise
        except Exception:
            # Never expose provider payloads, purchase tokens or raw errors.
            # Caller maps this to 503; DB/provider failure grants no rights.
            raise PlayBoundaryError("PLAY_VERIFICATION_UNAVAILABLE") from None
