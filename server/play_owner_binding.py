"""SQLite token-to-owner binding ledger. Server-only; never trust client owner IDs.

Bind only after independent authentication and verified provider lookup.
Database file must be protected by host filesystem permissions.
"""
import hmac
import sqlite3
from server.play_entitlement_gate import token_digest


class OwnershipConflict(PermissionError):
    pass


def initialize(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS play_token_owners (
        token_sha256 TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        created_at_ms INTEGER NOT NULL
    )""")
    db.commit()


def bind_or_verify_owner(db: sqlite3.Connection, *, purchase_token: str,
                         authenticated_owner_id: str, now_ms: int) -> str:
    """Atomically bind first claimant; deny any subsequent conflicting claimant.

    Must only be called after successful Google Play verification. This
    prevents reassignment but cannot prove the first claimant is legitimate;
    Play obfuscatedExternalAccountId and authenticated account binding
    remain necessary before production.
    """
    if not isinstance(authenticated_owner_id, str) or not authenticated_owner_id.strip():
        raise ValueError("INVALID_AUTHENTICATED_OWNER")
    if not isinstance(now_ms, int) or isinstance(now_ms, bool) or now_ms < 0:
        raise ValueError("INVALID_TIMESTAMP")
    digest = token_digest(purchase_token)
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute("INSERT OR IGNORE INTO play_token_owners (token_sha256,owner_id,created_at_ms) VALUES (?,?,?)",
                   (digest, authenticated_owner_id, now_ms))
        row = db.execute("SELECT owner_id FROM play_token_owners WHERE token_sha256=?", (digest,)).fetchone()
        if row is None or not hmac.compare_digest(row[0], authenticated_owner_id):
            raise OwnershipConflict("PURCHASE_TOKEN_ALREADY_BOUND")
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return digest
