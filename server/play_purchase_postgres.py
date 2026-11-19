"""Provider-verified purchase registration in the same PostgreSQL RTDN ledger.

Only the authenticated server boundary may use this store. A verification
transaction never binds an owner before fresh Play verification authorizes
the injected binder. Diagnostic snapshots remain separate from access rights.
"""
from contextlib import closing, contextmanager
import hmac
import re

import psycopg
from psycopg import sql
from psycopg.pq import TransactionStatus

from server.play_entitlement_gate import token_digest
from server.play_google_api import TOKEN_RE
from server.play_owner_binding import OwnershipConflict
from server.play_rtdn_postgres import (
    PostgresRtdnStore, _digest, _lock_key, _table, record_postgres_snapshot,
)
from server.play_rtdn_store import RtdnStoreUnavailable

_OWNER = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_MAX_TIME_MS = 4102444800000


def _owner(value):
    if not isinstance(value, str) or not _OWNER.fullmatch(value):
        raise ValueError("INVALID_AUTHENTICATED_OWNER")
    return value


class _Verification:
    def __init__(self, connection, schema, token_sha256, authenticated_owner_id):
        self.connection = connection
        self.schema = schema
        self.token_sha256 = token_sha256
        self.owner = authenticated_owner_id

    def _require_transaction(self, connection):
        if (connection is not self.connection or
                connection.info.transaction_status != TransactionStatus.INTRANS):
            raise RtdnStoreUnavailable("PLAY_STORE_TRANSACTION_INVALID")

    def observation_time_ms(self, clock=None):
        self._require_transaction(self.connection)
        return self.connection.execute(
            "SELECT pg_catalog.floor(EXTRACT(EPOCH FROM pg_catalog.clock_timestamp()) * 1000)::bigint"
        ).fetchone()[0]

    def assert_owner(self):
        row = self.connection.execute(sql.SQL(
            "SELECT owner_id FROM {} WHERE token_sha256=%s FOR SHARE"
        ).format(_table(self.schema, "play_token_owners")), (self.token_sha256,)).fetchone()
        if row is not None and not hmac.compare_digest(row[0], self.owner):
            raise OwnershipConflict("PURCHASE_TOKEN_ALREADY_BOUND")

    def bind_verified_owner(self, connection, *, purchase_token,
                            authenticated_owner_id, now_ms):
        """Register only after caller's verified entitlement check; never commit."""
        self._require_transaction(connection)
        _owner(authenticated_owner_id)
        if (not isinstance(purchase_token, str) or not 1 <= len(purchase_token) <= 4096 or
                not TOKEN_RE.fullmatch(purchase_token)):
            raise ValueError("INVALID_PURCHASE_TOKEN")
        if type(now_ms) is not int or not 0 <= now_ms <= _MAX_TIME_MS:
            raise ValueError("INVALID_TIMESTAMP")
        digest = token_digest(purchase_token)
        if (not hmac.compare_digest(digest, self.token_sha256) or
                not hmac.compare_digest(authenticated_owner_id, self.owner)):
            raise OwnershipConflict("PURCHASE_REGISTRATION_SCOPE_MISMATCH")
        connection.execute(sql.SQL("INSERT INTO {} (token_sha256,owner_id) "
            "VALUES(%s,%s) ON CONFLICT(token_sha256) DO NOTHING").format(
                _table(self.schema, "play_token_owners")), (digest, authenticated_owner_id))
        row = connection.execute(sql.SQL(
            "SELECT owner_id FROM {} WHERE token_sha256=%s FOR UPDATE"
        ).format(_table(self.schema, "play_token_owners")), (digest,)).fetchone()
        if row is None or not hmac.compare_digest(row[0], authenticated_owner_id):
            raise OwnershipConflict("PURCHASE_TOKEN_ALREADY_BOUND")
        return digest

    def record_snapshot(self, connection, purchase, *, server_secret, observed_at_ms):
        """Persist trusted evidence with the owner binding in this transaction."""
        self._require_transaction(connection)
        if (not isinstance(getattr(purchase, "purchase_token_sha256", None), str) or
                not hmac.compare_digest(purchase.purchase_token_sha256, self.token_sha256) or
                not isinstance(getattr(purchase, "owner_id", None), str) or
                not hmac.compare_digest(purchase.owner_id, self.owner)):
            raise OwnershipConflict("PURCHASE_SNAPSHOT_SCOPE_MISMATCH")
        return record_postgres_snapshot(connection, purchase, server_secret=server_secret,
            observed_at_ms=observed_at_ms, schema=self.schema)


class PostgresPlayStore(PostgresRtdnStore):
    """One explicitly migrated store for purchase registration and RTDN.

    A per-token transaction lock spans GET/optional ACK/fresh GET. Independent
    verification workers therefore cannot acknowledge the same token in
    parallel. External ACK success cannot be rolled back by a database error;
    subsequent requests still require fresh provider verification before grant.
    """
    @contextmanager
    def verification(self, *, token_sha256, authenticated_owner_id):
        _digest(token_sha256)
        _owner(authenticated_owner_id)
        try:
            with closing(self.db_factory()) as connection:
                if connection.info.transaction_status != TransactionStatus.IDLE:
                    raise RtdnStoreUnavailable("PLAY_POSTGRES_SESSION_NOT_IDLE")
                with connection.transaction():
                    connection.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                    connection.execute("SET LOCAL search_path TO pg_catalog")
                    connection.execute("SET LOCAL lock_timeout = '10s'")
                    connection.execute("SELECT pg_catalog.pg_advisory_xact_lock(%s)",
                        (_lock_key(self.schema, "verification", token_sha256),))
                    verification = _Verification(connection, self.schema,
                                                 token_sha256, authenticated_owner_id)
                    verification.assert_owner()
                    yield verification
        except (psycopg.Error, OSError):
            raise RtdnStoreUnavailable("PLAY_POSTGRES_UNAVAILABLE") from None
