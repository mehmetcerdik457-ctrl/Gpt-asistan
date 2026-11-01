"""SQLite-backed SHA-256 idempotency ledger."""
from __future__ import annotations
import hashlib, json, re, sqlite3
_KEY = re.compile(r"[A-Za-z0-9._:-]{8,128}")

def request_digest(payload) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()

def key_digest(key: str) -> str:
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        raise ValueError("Idempotency-Key must be 8-128 safe ASCII characters")
    return hashlib.sha256(key.encode()).hexdigest()

def initialize(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS idempotency_ledger(
        key_sha256 TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('processing','completed','failed')),
        response_json TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)""")

def reserve(db: sqlite3.Connection, key: str, payload_hash: str):
    hashed = key_digest(key)
    if not re.fullmatch(r"[a-f0-9]{64}", payload_hash):
        raise ValueError("invalid payload SHA-256")
    db.execute("BEGIN IMMEDIATE")
    row = db.execute("SELECT request_sha256,state,response_json FROM idempotency_ledger WHERE key_sha256=?", (hashed,)).fetchone()
    if row:
        old_hash, state, response = row
        if old_hash != payload_hash:
            raise ValueError("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD")
        if state == "completed":
            return json.loads(response)
        if state == "processing":
            raise RuntimeError("IDEMPOTENCY_REQUEST_IN_PROGRESS")
        db.execute("UPDATE idempotency_ledger SET state='processing',response_json=NULL,updated_at=strftime('%s','now') WHERE key_sha256=?", (hashed,))
    else:
        db.execute("INSERT INTO idempotency_ledger VALUES(?,?, 'processing',NULL,strftime('%s','now'),strftime('%s','now'))", (hashed,payload_hash))
    return None

def complete(db: sqlite3.Connection, key: str, payload_hash: str, response: dict) -> None:
    cur = db.execute("UPDATE idempotency_ledger SET state='completed',response_json=?,updated_at=strftime('%s','now') WHERE key_sha256=? AND request_sha256=? AND state='processing'",
        (json.dumps(response,ensure_ascii=False,separators=(',',':')),key_digest(key),payload_hash))
    if cur.rowcount != 1: raise RuntimeError("IDEMPOTENCY_LEDGER_STATE_MISMATCH")

def fail(db: sqlite3.Connection, key: str, payload_hash: str) -> None:
    db.execute("UPDATE idempotency_ledger SET state='failed',updated_at=strftime('%s','now') WHERE key_sha256=? AND request_sha256=? AND state='processing'",
        (key_digest(key),payload_hash))
