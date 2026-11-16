"""Transaction boundary for authenticated RTDN processing.

The delivery transaction owns both diagnostic snapshots and the success
audit. A duplicate must be checked under a writer lock, before Google is
called. Schema installation remains a separate trusted operation.
"""
from contextlib import closing, contextmanager
import hmac
import sqlite3


class RtdnStoreConflict(ValueError):
    """The same delivery ID was reused for a different payload."""


class RtdnStoreUnavailable(RuntimeError):
    """A fixed, non-sensitive store failure; the delivery must be retried."""


class _SQLiteDelivery:
    def __init__(self, db, message_digest, payload_digest):
        self.connection = db
        self.message_digest = message_digest
        self.payload_digest = payload_digest
        self.finished = False
        old = db.execute(
            "SELECT payload_digest FROM play_rtdn_audit WHERE message_digest=?",
            (message_digest,),
        ).fetchone()
        self.duplicate = old is not None
        if old is not None and not hmac.compare_digest(old[0], payload_digest):
            raise RtdnStoreConflict("RTDN_MESSAGE_ID_CONFLICT")

    def owner_for(self, token_hash):
        row = self.connection.execute(
            "SELECT owner_id FROM play_token_owners WHERE token_sha256=?",
            (token_hash,),
        ).fetchone()
        return row[0] if row else None

    def observation_time_ms(self, clock):
        return int(clock() * 1000)

    def finish(self, *, token_digest, outcome, recorded_at_ms):
        if self.duplicate or self.finished or not self.connection.in_transaction:
            raise RtdnStoreUnavailable("RTDN_STORE_TRANSACTION_INVALID")
        self.connection.execute(
            "INSERT INTO play_rtdn_audit "
            "(message_digest,payload_digest,purchase_token_digest,outcome,recorded_at_ms) "
            "VALUES(?,?,?,?,?)",
            (self.message_digest, self.payload_digest, token_digest,
             outcome, recorded_at_ms),
        )
        self.finished = True


class SQLiteRtdnStore:
    """Serialize SQLite writers for the full recheck/snapshot/audit transaction.

    Use PostgreSQL for independent servers. SQLite must refer to the same
    protected local database file; separate local files do not share locks.
    """
    def __init__(self, db_factory):
        self.db_factory = db_factory

    @contextmanager
    def delivery(self, message_digest, payload_digest):
        try:
            with closing(self.db_factory()) as db:
                if db.in_transaction:
                    raise RtdnStoreUnavailable("RTDN_STORE_TRANSACTION_INVALID")
                db.execute("BEGIN IMMEDIATE")
                try:
                    delivery = _SQLiteDelivery(db, message_digest, payload_digest)
                    yield delivery
                    if not delivery.duplicate and not delivery.finished:
                        raise RtdnStoreUnavailable("RTDN_STORE_TRANSACTION_INCOMPLETE")
                    db.commit()
                except BaseException:
                    db.rollback()
                    raise
        except (sqlite3.Error, OSError):
            raise RtdnStoreUnavailable("RTDN_STORE_UNAVAILABLE") from None
