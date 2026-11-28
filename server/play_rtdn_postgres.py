"""Explicit PostgreSQL storage for authenticated RTDN reconciliation.

No migration runs on a request path. Message locks, provider-backed snapshot
updates and successful audit insertion share one transaction. This ledger is
diagnostic evidence, never an entitlement cache or a purchase-token registry.
"""
from contextlib import closing, contextmanager
import hashlib
import hmac
import re

import psycopg
from psycopg import sql
from psycopg.pq import TransactionStatus

from server.play_rtdn_store import RtdnStoreConflict, RtdnStoreUnavailable
from server.play_verified_snapshot import SnapshotRejected, validated_snapshot_values

_SHA = re.compile(r"[a-f0-9]{64}\Z")
_SCHEMA = re.compile(r"[a-z][a-z0-9_]{0,62}\Z")
_OUTCOMES = frozenset(("TEST", "RECHECKED_BOUND", "RECHECKED_UNBOUND"))
_MAX_TIME_MS = 4102444800000


def _schema(value):
    if not isinstance(value, str) or not _SCHEMA.fullmatch(value):
        raise ValueError("RTDN_POSTGRES_SCHEMA_INVALID")
    return value


def _table(schema, table):
    return sql.Identifier(schema, table)


def _digest(value):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ValueError("RTDN_DIGEST_INVALID")
    return value


def _lock_key(schema, kind, *values):
    # Advisory locks are transaction-scoped and shared across processes. The
    # schema and operation namespace prevent accidental cross-ledger locking.
    material = "\0".join(("orba-rtdn-v1", schema, kind, *values)).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big", signed=True)


def initialize_postgres_rtdn(connection, *, schema="orba"):
    """Trusted installer migration; caller supplies an idle private DB session."""
    schema = _schema(schema)
    if connection.info.transaction_status != TransactionStatus.IDLE:
        raise RtdnStoreUnavailable("RTDN_POSTGRES_MIGRATION_REQUIRES_IDLE_SESSION")
    try:
        with connection.transaction():
            connection.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                sql.Identifier(schema)))
            connection.execute(sql.SQL("""CREATE TABLE IF NOT EXISTS {} (
                message_digest TEXT PRIMARY KEY CHECK(message_digest ~ '^[a-f0-9]{{64}}$'),
                payload_digest TEXT NOT NULL CHECK(payload_digest ~ '^[a-f0-9]{{64}}$'),
                purchase_token_digest TEXT CHECK(purchase_token_digest ~ '^[a-f0-9]{{64}}$'),
                outcome TEXT NOT NULL CHECK(outcome IN
                    ('TEST','RECHECKED_BOUND','RECHECKED_UNBOUND')),
                recorded_at_ms BIGINT NOT NULL CHECK(recorded_at_ms BETWEEN 0 AND 4102444800000),
                CHECK((outcome='TEST' AND purchase_token_digest IS NULL) OR
                      (outcome<>'TEST' AND purchase_token_digest IS NOT NULL))
            )""").format(_table(schema, "play_rtdn_audit")))
            connection.execute(sql.SQL("""CREATE TABLE IF NOT EXISTS {} (
                token_sha256 TEXT PRIMARY KEY CHECK(token_sha256 ~ '^[a-f0-9]{{64}}$'),
                owner_id TEXT NOT NULL CHECK(owner_id ~ '^[A-Za-z0-9_-]{{1,64}}$')
            )""").format(_table(schema, "play_token_owners")))
            connection.execute(sql.SQL("""CREATE TABLE IF NOT EXISTS {} (
                purchase_token_sha256 TEXT NOT NULL CHECK(purchase_token_sha256 ~ '^[a-f0-9]{{64}}$'),
                product_id TEXT NOT NULL,
                owner_hmac TEXT NOT NULL CHECK(owner_hmac ~ '^[a-f0-9]{{64}}$'),
                provider_state TEXT NOT NULL,
                expiry_ms BIGINT NOT NULL CHECK(expiry_ms BETWEEN 1 AND 4102444800000),
                acknowledged INTEGER NOT NULL CHECK(acknowledged IN (0,1)),
                historical_access INTEGER NOT NULL CHECK(historical_access IN (0,1)),
                observed_at_ms BIGINT NOT NULL CHECK(observed_at_ms BETWEEN 0 AND 4102444800000),
                PRIMARY KEY(purchase_token_sha256, product_id)
            )""").format(_table(schema, "play_verified_snapshots")))
    except psycopg.Error:
        raise RtdnStoreUnavailable("RTDN_POSTGRES_MIGRATION_UNAVAILABLE") from None


class _Delivery:
    def __init__(self, connection, schema, message_digest, payload_digest, duplicate):
        self.connection = connection
        self.schema = schema
        self.message_digest = message_digest
        self.payload_digest = payload_digest
        self.duplicate = duplicate
        self.finished = duplicate

    def observation_time_ms(self, clock=None):
        """Use the shared DB clock, never a possibly skewed worker clock."""
        return self.connection.execute(
            "SELECT pg_catalog.floor(EXTRACT(EPOCH FROM pg_catalog.clock_timestamp()) * 1000)::bigint"
        ).fetchone()[0]

    def owner_for(self, token_hash):
        _digest(token_hash)
        row = self.connection.execute(sql.SQL(
            "SELECT owner_id FROM {} WHERE token_sha256=%s FOR SHARE"
        ).format(_table(self.schema, "play_token_owners")), (token_hash,)).fetchone()
        return row[0] if row is not None else None

    def finish(self, *, token_digest, outcome, recorded_at_ms):
        if self.finished:
            raise RtdnStoreUnavailable("RTDN_DELIVERY_ALREADY_FINISHED")
        if (outcome not in _OUTCOMES or type(recorded_at_ms) is not int or
                not 0 <= recorded_at_ms <= _MAX_TIME_MS or
                (outcome == "TEST") != (token_digest is None)):
            raise ValueError("RTDN_AUDIT_INVALID")
        if token_digest is not None:
            _digest(token_digest)
        self.connection.execute(sql.SQL("""INSERT INTO {}
            (message_digest,payload_digest,purchase_token_digest,outcome,recorded_at_ms)
            VALUES(%s,%s,%s,%s,%s)""").format(_table(self.schema, "play_rtdn_audit")),
            (self.message_digest, self.payload_digest, token_digest, outcome, recorded_at_ms))
        self.finished = True


class PostgresRtdnStore:
    """Owns one connection/transaction per delivery; safe across worker processes.

    db_factory must return a fresh idle psycopg connection. Use a bounded
    provider timeout; the message lock intentionally spans provider I/O.
    Lock waits are limited to 10 seconds, after which Pub/Sub can redeliver.
    """
    def __init__(self, db_factory, *, schema="orba"):
        if not callable(db_factory):
            raise ValueError("RTDN_POSTGRES_FACTORY_INVALID")
        self.db_factory = db_factory
        self.schema = _schema(schema)

    @contextmanager
    def delivery(self, message_digest, payload_digest):
        _digest(message_digest)
        _digest(payload_digest)
        try:
            with closing(self.db_factory()) as connection:
                if connection.info.transaction_status != TransactionStatus.IDLE:
                    raise RtdnStoreUnavailable("RTDN_POSTGRES_SESSION_NOT_IDLE")
                with connection.transaction():
                    # READ COMMITTED is required: after waiting for another
                    # worker's lock, the following SELECT must see its commit.
                    connection.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                    connection.execute("SET LOCAL search_path TO pg_catalog")
                    connection.execute("SET LOCAL lock_timeout = '10s'")
                    connection.execute("SELECT pg_catalog.pg_advisory_xact_lock(%s)",
                        (_lock_key(self.schema, "message", message_digest),))
                    row = connection.execute(sql.SQL(
                        "SELECT payload_digest FROM {} WHERE message_digest=%s"
                    ).format(_table(self.schema, "play_rtdn_audit")),
                        (message_digest,)).fetchone()
                    if row is not None and not hmac.compare_digest(row[0], payload_digest):
                        raise RtdnStoreConflict("RTDN_MESSAGE_ID_CONFLICT")
                    delivery = _Delivery(connection, self.schema, message_digest,
                                         payload_digest, row is not None)
                    yield delivery
                    if not delivery.finished:
                        raise RtdnStoreUnavailable("RTDN_DELIVERY_NOT_FINISHED")
        except (psycopg.Error, OSError):
            # Never expose connection strings, credentials or SQL arguments.
            raise RtdnStoreUnavailable("RTDN_POSTGRES_UNAVAILABLE") from None


def record_postgres_snapshot(connection, purchase, *, server_secret,
                             observed_at_ms, schema="orba"):
    """Record trusted provider evidence in the caller's active transaction.

    No commit or rollback occurs here. The caller must roll back on any
    exception so snapshot and RTDN audit cannot be committed independently.
    """
    schema = _schema(schema)
    if connection.info.transaction_status != TransactionStatus.INTRANS:
        raise RtdnStoreUnavailable("RTDN_SNAPSHOT_REQUIRES_TRANSACTION")
    values = validated_snapshot_values(purchase, server_secret=server_secret,
                                      observed_at_ms=observed_at_ms)
    token_hash, product_id = purchase.purchase_token_sha256, purchase.product_id
    try:
        connection.execute("SELECT pg_catalog.pg_advisory_xact_lock(%s)",
            (_lock_key(schema, "snapshot", token_hash, product_id),))
        row = connection.execute(sql.SQL("""SELECT owner_hmac,provider_state,
            expiry_ms,acknowledged,historical_access,observed_at_ms FROM {}
            WHERE purchase_token_sha256=%s AND product_id=%s FOR UPDATE""").format(
                _table(schema, "play_verified_snapshots")), (token_hash, product_id)).fetchone()
        if row is not None:
            if not hmac.compare_digest(row[0], values[0]):
                raise SnapshotRejected("SNAPSHOT_OWNER_CONFLICT")
            if observed_at_ms < row[5]:
                return False
            if observed_at_ms == row[5]:
                if tuple(row) != values:
                    raise SnapshotRejected("SNAPSHOT_CLOCK_TIE_CONFLICT")
                return False
            connection.execute(sql.SQL("""UPDATE {} SET owner_hmac=%s,
                provider_state=%s,expiry_ms=%s,acknowledged=%s,historical_access=%s,
                observed_at_ms=%s WHERE purchase_token_sha256=%s AND product_id=%s""").format(
                    _table(schema, "play_verified_snapshots")), values + (token_hash, product_id))
        else:
            connection.execute(sql.SQL("""INSERT INTO {} (owner_hmac,provider_state,
                expiry_ms,acknowledged,historical_access,observed_at_ms,
                purchase_token_sha256,product_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""").format(
                    _table(schema, "play_verified_snapshots")), values + (token_hash, product_id))
        return True
    except psycopg.Error:
        raise RtdnStoreUnavailable("RTDN_POSTGRES_SNAPSHOT_UNAVAILABLE") from None
