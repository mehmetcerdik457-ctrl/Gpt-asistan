"""Provider-verified subscription snapshot; never a cached entitlement grant.

The snapshots capture *evidence* from authenticated Google Play v2 GET calls,
not authority to unlock paid features. Every access request still requires a
fresh Google API lookup through the owner-signed gateway. This module has no
public HTTP route, no secret keys and no background network activity.
"""
from __future__ import annotations
import hmac
import re
import sqlite3

from server.play_account_id import obfuscated_play_account_id
from server.play_entitlement_gate import (
    PACKAGE, PRODUCT_RE, VerifiedPlayPurchase, entitlement_allowed,
    token_digest,
)

SHA = re.compile(r"^[a-f0-9]{64}$")
MAX_TIME_MS = 4102444800000


class SnapshotRejected(ValueError):
    """A fixed error with no purchase or owner identifier."""


def initialize_snapshot(db: sqlite3.Connection) -> None:
    """Schema must be migrated by trusted installer, never the public gateway."""
    db.execute("""CREATE TABLE IF NOT EXISTS play_verified_snapshots (
        purchase_token_sha256 TEXT NOT NULL,
        product_id TEXT NOT NULL,
        owner_hmac TEXT NOT NULL,
        provider_state TEXT NOT NULL,
        expiry_ms INTEGER NOT NULL,
        acknowledged INTEGER NOT NULL CHECK(acknowledged IN (0,1)),
        historical_access INTEGER NOT NULL CHECK(historical_access IN (0,1)),
        observed_at_ms INTEGER NOT NULL,
        PRIMARY KEY (purchase_token_sha256, product_id)
    )""")
    db.commit()


def _valid_owner(owner: str, secret: bytes) -> str:
    if (not isinstance(owner, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", owner) or
            not isinstance(secret, bytes) or len(secret) < 32):
        raise SnapshotRejected("SNAPSHOT_IDENTITY_INVALID")
    return obfuscated_play_account_id(
        authenticated_owner_id=owner, server_secret=secret)


def record_verified_snapshot(db: sqlite3.Connection, purchase: VerifiedPlayPurchase,
                             *, server_secret: bytes, observed_at_ms: int) -> bool:
    """Upsert only provider-verified evidence, monotonically by check start time.

    Return True when a newer observation committed; False on exact replay or
    older observation. A tie with different data fails closed rather than
    allowing last-writer-wins access-state resurrection.
    """
    if (type(purchase) is not VerifiedPlayPurchase or
            purchase.verified_by_google_api is not True or
            purchase.package_name != PACKAGE or
            not isinstance(purchase.product_id, str) or
            not PRODUCT_RE.fullmatch(purchase.product_id) or
            not isinstance(purchase.purchase_token_sha256, str) or
            not SHA.fullmatch(purchase.purchase_token_sha256) or
            not isinstance(purchase.subscription_state, str) or
            not re.fullmatch(r"[A-Z_]{1,96}", purchase.subscription_state) or
            type(purchase.expires_at_ms) is not int or
            not 0 < purchase.expires_at_ms <= MAX_TIME_MS or
            type(purchase.acknowledged) is not bool or
            type(observed_at_ms) is not int or
            not 0 <= observed_at_ms <= MAX_TIME_MS):
        raise SnapshotRejected("SNAPSHOT_PROVENANCE_INVALID")
    owner_hmac = _valid_owner(purchase.owner_id, server_secret)
    historical = int(entitlement_allowed(
        purchase, owner_id=purchase.owner_id, product_id=purchase.product_id,
        token_sha256=purchase.purchase_token_sha256, now_ms=observed_at_ms))
    values = (
        owner_hmac, purchase.subscription_state, purchase.expires_at_ms,
        int(purchase.acknowledged), historical, observed_at_ms,
    )
    # SQLite IMMEDIATE transaction serializes concurrent writers. No partial
    # snapshot is committed on owner conflict or same-timestamp disagreement.
    db.execute("BEGIN IMMEDIATE")
    try:
        old = db.execute(
            "SELECT owner_hmac,provider_state,expiry_ms,acknowledged,"
            "historical_access,observed_at_ms FROM play_verified_snapshots "
            "WHERE purchase_token_sha256=? AND product_id=?",
            (purchase.purchase_token_sha256, purchase.product_id)
        ).fetchone()
        if old is not None:
            if not hmac.compare_digest(old[0], owner_hmac):
                raise SnapshotRejected("SNAPSHOT_OWNER_CONFLICT")
            if observed_at_ms < old[5]:
                db.commit()
                return False
            if observed_at_ms == old[5]:
                if tuple(old) != values:
                    raise SnapshotRejected("SNAPSHOT_CLOCK_TIE_CONFLICT")
                db.commit()
                return False
            db.execute(
                "UPDATE play_verified_snapshots SET owner_hmac=?,provider_state=?,"
                "expiry_ms=?,acknowledged=?,historical_access=?,observed_at_ms=? "
                "WHERE purchase_token_sha256=? AND product_id=?",
                values + (purchase.purchase_token_sha256, purchase.product_id))
        else:
            db.execute(
                "INSERT INTO play_verified_snapshots "
                "(owner_hmac,provider_state,expiry_ms,acknowledged,"
                "historical_access,observed_at_ms,purchase_token_sha256,product_id) "
                "VALUES(?,?,?,?,?,?,?,?)",
                values + (purchase.purchase_token_sha256, purchase.product_id))
        db.commit()
        return True
    except BaseException:
        db.rollback()
        raise


def diagnostic_snapshot(db: sqlite3.Connection, *, owner_id: str,
                        purchase_token: str, product_id: str,
                        server_secret: bytes, now_ms: int):
    """Private, NON-authoritative diagnostic. Does not issue access rights.

    Only the owner-aware authenticated server may call this function.
    In particular historical_access=True NEVER implies authorization.
    """
    owner_hmac = _valid_owner(owner_id, server_secret)
    if (not isinstance(product_id, str) or not PRODUCT_RE.fullmatch(product_id) or
            type(now_ms) is not int or now_ms < 0):
        raise SnapshotRejected("SNAPSHOT_QUERY_INVALID")
    digest = token_digest(purchase_token)
    row = db.execute(
        "SELECT owner_hmac,provider_state,expiry_ms,acknowledged,"
        "historical_access,observed_at_ms FROM play_verified_snapshots "
        "WHERE purchase_token_sha256=? AND product_id=?",
        (digest, product_id)).fetchone()
    if row is None or not hmac.compare_digest(row[0], owner_hmac):
        return None
    return {
        "last_provider_state": row[1],
        "recorded_expiry_ms": row[2],
        "last_checked_at_ms": row[5],
        "expired_at_query": now_ms >= row[2],
        "historically_allowed_at_check": bool(row[4]),
        "requires_live_google_verification": True,
    }
