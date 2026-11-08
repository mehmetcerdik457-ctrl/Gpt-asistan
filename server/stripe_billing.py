"""Fail-closed Stripe billing event receiver for KRAL/ORBA (Python stdlib).

Mount behind a trusted HTTPS reverse proxy. This is intentionally not a public
unauthenticated subscription-listing API or a Google Play billing replacement.

Required: STRIPE_WEBHOOK_SECRET, BILLING_DB (private absolute path).
No Stripe secret keys, user email addresses, or card details are stored.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_EVENT_BYTES = 131072
WEBHOOK_TOLERANCE_SECONDS = 300
EVENT_TYPES = {
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_failed",
    "invoice.paid",
}
STRIPE_ID_RE = re.compile(r"^[A-Za-z0-9_]{3,128}$")


class BillingError(ValueError):
    def __init__(self, reason: str, code: int = 400):
        super().__init__(reason)
        self.code = code


def _valid_id(value: object, prefix: str) -> bool:
    return isinstance(value, str) and value.startswith(prefix) and bool(STRIPE_ID_RE.fullmatch(value))


def verify_signature(payload: bytes, header: str, secret: str, now: int | None = None) -> int:
    if not isinstance(payload, bytes) or not isinstance(header, str) or not secret or not secret.startswith("whsec_"):
        raise BillingError("SIGNATURE_CONFIGURATION_INVALID", 503)
    fields = [field.strip().split("=", 1) for field in header.split(",") if "=" in field]
    timestamps = [v for k, v in fields if k == "t" and v.isascii() and v.isdigit()]
    signatures = [v for k, v in fields if k == "v1" and re.fullmatch(r"[a-fA-F0-9]{64}", v)]
    if len(timestamps) != 1 or not signatures:
        raise BillingError("SIGNATURE_MISSING", 400)
    stamp = int(timestamps[0])
    current = int(time.time()) if now is None else int(now)
    if abs(current - stamp) > WEBHOOK_TOLERANCE_SECONDS:
        raise BillingError("SIGNATURE_EXPIRED", 400)
    expected = hmac.new(secret.encode("utf-8"), str(stamp).encode() + b"." + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, value.lower()) for value in signatures):
        raise BillingError("SIGNATURE_INVALID", 400)
    return stamp


def connect_db(path: str) -> sqlite3.Connection:
    p = Path(path)
    if not p.is_absolute() or not p.parent.is_dir():
        raise BillingError("BILLING_DB_INVALID", 503)
    db = sqlite3.connect(path, timeout=5)
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("PRAGMA journal_mode=WAL")
    requested_mode = os.getenv("STRIPE_LIVEMODE")
    if requested_mode not in ("true", "false"):
        db.close()
        raise BillingError("STRIPE_LIVEMODE_MUST_BE_EXPLICIT", 503)
    db.execute("""CREATE TABLE IF NOT EXISTS stripe_environment (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        mode TEXT NOT NULL CHECK(mode IN ('true', 'false'))
    )""")
    with db:
        db.execute("BEGIN IMMEDIATE")
        pinned = db.execute("SELECT mode FROM stripe_environment WHERE singleton=1").fetchone()
        if pinned is None:
            db.execute("INSERT INTO stripe_environment(singleton,mode) VALUES(1,?)", (requested_mode,))
        elif pinned[0] != requested_mode:
            db.close()
            raise BillingError("STRIPE_DB_ENVIRONMENT_MISMATCH", 403)
    db.execute("""CREATE TABLE IF NOT EXISTS stripe_events (
        event_id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        created INTEGER NOT NULL,
        recorded_at INTEGER NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS stripe_subscriptions (
        subscription_id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL,
        status TEXT NOT NULL,
        cancel_at_period_end INTEGER NOT NULL,
        last_event_created INTEGER NOT NULL,
        last_event_id TEXT NOT NULL
    )""")
    db.commit()
    os.chmod(path, 0o600)
    return db


def _get_object(event: dict) -> dict:
    data = event.get("data")
    obj = data.get("object") if isinstance(data, dict) else None
    if not isinstance(obj, dict):
        raise BillingError("EVENT_OBJECT_INVALID")
    return obj


def process_event(db: sqlite3.Connection, payload: bytes, header: str, secret: str, *, now: int | None = None) -> dict:
    if len(payload) > MAX_EVENT_BYTES:
        raise BillingError("EVENT_TOO_LARGE", 413)
    verify_signature(payload, header, secret, now)
    try:
        event = json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        raise BillingError("EVENT_JSON_INVALID") from None
    if not isinstance(event, dict) or event.get("livemode") is not False and event.get("livemode") is not True:
        raise BillingError("EVENT_INVALID")
    event_id, event_type, created = event.get("id"), event.get("type"), event.get("created")
    if not _valid_id(event_id, "evt_") or not isinstance(event_type, str) or not isinstance(created, int) or isinstance(created, bool) or created < 0:
        raise BillingError("EVENT_METADATA_INVALID")
    # Prevent accidental cross-mode contamination. Production requires explicit deployment mode.
    mode = os.getenv("STRIPE_LIVEMODE")
    if mode not in ("true", "false"):
        raise BillingError("STRIPE_LIVEMODE_MUST_BE_EXPLICIT", 503)
    target_live = mode == "true"
    if event["livemode"] is not target_live:
        raise BillingError("STRIPE_MODE_MISMATCH", 403)
    obj = _get_object(event) if event_type in EVENT_TYPES else None
    with db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM stripe_events WHERE event_id=?", (event_id,)).fetchone():
            return {"received": True, "duplicate": True}
        if event_type.startswith("customer.subscription.") and event_type in EVENT_TYPES:
            sid, customer = obj.get("id"), obj.get("customer")
            if not _valid_id(sid, "sub_") or not _valid_id(customer, "cus_"):
                raise BillingError("SUBSCRIPTION_INVALID")
            valid_states = {"trialing", "active", "past_due", "unpaid", "canceled", "incomplete", "incomplete_expired", "paused"}
            status = "canceled" if event_type.endswith(".deleted") else obj.get("status")
            if status not in valid_states:
                raise BillingError("SUBSCRIPTION_STATUS_INVALID")
            cancel_at_period_end = 1 if obj.get("cancel_at_period_end") is True else 0
            prior = db.execute("SELECT last_event_created,last_event_id,status FROM stripe_subscriptions WHERE subscription_id=?", (sid,)).fetchone()
            # A Stripe subscription ID cannot legitimately become active again after deletion.
            # Out-of-order deliveries and same-second events must not revive canceled access.
            is_terminal = prior is not None and prior[2] == "canceled"
            if not is_terminal and (not prior or status == "canceled" or (created, event_id) > (prior[0], prior[1])):
                db.execute("""INSERT INTO stripe_subscriptions(subscription_id,customer_id,status,cancel_at_period_end,last_event_created,last_event_id)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(subscription_id) DO UPDATE SET
                    customer_id=excluded.customer_id, status=excluded.status,
                    cancel_at_period_end=excluded.cancel_at_period_end,
                    last_event_created=excluded.last_event_created,last_event_id=excluded.last_event_id""",
                    (sid,customer,status,cancel_at_period_end,created,event_id))
        # Invoices are audited as event receipts, never grant paid access by themselves.
        db.execute("INSERT INTO stripe_events(event_id,event_type,created,recorded_at) VALUES(?,?,?,?)",
                   (event_id,event_type[:100],created,int(time.time())))
    return {"received": True, "duplicate": False}


def can_access(db: sqlite3.Connection, subscription_id: str) -> bool:
    """Use only behind independently authenticated, customer-bound access checks."""
    row = db.execute("SELECT status FROM stripe_subscriptions WHERE subscription_id=?", (subscription_id,)).fetchone()
    return bool(row and row[0] in ("active", "trialing"))


class Handler(BaseHTTPRequestHandler):
    server_version = "ORBA-StripeBridge/0.1"

    def do_POST(self):
        if self.path != "/api/billing/stripe/webhook":
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "-1"))
            if size < 0 or size > MAX_EVENT_BYTES:
                raise BillingError("EVENT_SIZE_INVALID", 413)
            secret, path = os.getenv("STRIPE_WEBHOOK_SECRET", ""), os.getenv("BILLING_DB", "")
            if not secret or not path:
                raise BillingError("BILLING_NOT_CONFIGURED", 503)
            payload = self.rfile.read(size)
            db = connect_db(path)
            try:
                response = process_event(db, payload, self.headers.get("Stripe-Signature", ""), secret)
            finally:
                db.close()
            status = 200
        except (BillingError, ValueError) as exc:
            status = exc.code if isinstance(exc, BillingError) else 400
            response = {"received": False, "error": str(exc)}
        except (sqlite3.Error, OSError):
            status, response = 503, {"received": False, "error": "BILLING_STORAGE_UNAVAILABLE"}
        encoded = json.dumps(response, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        return  # Webhook payloads, signatures, emails, and tokens must never be logged.


def main():
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    path = os.getenv("BILLING_DB", "")
    if not secret.startswith("whsec_") or not path or os.getenv("STRIPE_LIVEMODE") not in ("true", "false"):
        raise SystemExit("STRIPE_BRIDGE_DISABLED: private webhook secret, billing DB and explicit live/test mode required")
    with connect_db(path):
        pass
    bind = os.getenv("STRIPE_BIND", "127.0.0.1")
    port = int(os.getenv("STRIPE_PORT", "8091"))
    server = ThreadingHTTPServer((bind, port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
