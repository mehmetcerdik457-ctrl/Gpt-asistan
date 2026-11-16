"""SQLite transaction adapter for live-verified purchase ownership.

Owner binding and diagnostic evidence commit together. PostgreSQL uses the
same interface, allowing verification and RTDN to share one private ledger.
"""
from contextlib import closing, contextmanager
import hmac
import sqlite3

from server.play_owner_binding import bind_or_verify_owner, OwnershipConflict


class _SQLiteVerification:
    def __init__(self, connection):
        self.connection = connection

    def observation_time_ms(self, clock):
        return clock()

    def bind_verified_owner(self, db, **kwargs):
        if db is not self.connection:
            raise ValueError("PLAY_TRANSACTION_MISMATCH")
        return bind_or_verify_owner(db, **kwargs)


class SQLitePlayStore:
    def __init__(self, db_factory):
        self.db_factory = db_factory

    @contextmanager
    def verification(self, *, token_sha256, authenticated_owner_id):
        with closing(self.db_factory()) as db:
            if db.in_transaction:
                raise ValueError("PLAY_TRANSACTION_NOT_IDLE")
            db.execute("BEGIN IMMEDIATE")
            try:
                owner = db.execute(
                    "SELECT owner_id FROM play_token_owners WHERE token_sha256=?",
                    (token_sha256,),
                ).fetchone()
                if owner and not hmac.compare_digest(owner[0], authenticated_owner_id):
                    raise OwnershipConflict("PURCHASE_TOKEN_ALREADY_BOUND")
                yield _SQLiteVerification(db)
                db.commit()
            except BaseException:
                db.rollback()
                raise
