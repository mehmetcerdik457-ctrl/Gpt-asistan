"""Stripe merchant-only subscription mirror. No payment creation or entitlement bypass.

Run behind HTTPS reverse proxy; use private persistent SQLite and server-only keys.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY = 262_144
EVENT_TYPES = {
    "customer.subscription.created", "customer.subscription.updated",
    "customer.subscription.deleted", "checkout.session.completed",
    "invoice.paid", "invoice.payment_failed",
}
VALID_STATUSES = {"active", "trialing", "past_due", "unpaid", "canceled",
                  "incomplete", "incomplete_expired", "paused"}
IDENTIFIER = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")


class BillingError(ValueError):
    pass


def verify_stripe_signature(payload: bytes, header: str, secret: str, *, now=None) -> dict:
    """Verify t= and any v1= HMAC over the exact raw body; tolerance 5 minutes."""
    if not secret or not secret.startswith("whsec_"):
        raise BillingError("webhook_not_configured")
    if not isinstance(payload, bytes) or len(payload) > MAX_BODY:
        raise BillingError("invalid_payload")
    if not isinstance(header, str) or len(header) > 4096:
        raise BillingError("invalid_signature_header")
    fields = {}
    for part in header.split(","):
        key, sep, value = part.strip().partition("=")
        if sep and key in {"t", "v1"}:
            fields.setdefault(key, []).append(value)
    try:
        timestamp = int(fields["t"][0])
    except (KeyError, ValueError, IndexError):
        raise BillingError("invalid_signature_timestamp") from None
    current = int(time.time()) if now is None else int(now)
    if abs(current - timestamp) > 300:
        raise BillingError("stale_webhook")
    digest = hmac.new(secret.encode(), str(timestamp).encode() + b"." + payload,
                      hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(digest, value) for value in fields.get("v1", [])):
        raise BillingError("signature_mismatch")
    try:
        event = json.loads(payload)
    except (UnicodeDecodeError, ValueError):
        raise BillingError("invalid_json") from None
    if not isinstance(event, dict) or not isinstance(event.get("data"), dict):
        raise BillingError("invalid_event")
    if not isinstance(event.get("id"), str) or not IDENTIFIER.fullmatch(event["id"]):
        raise BillingError("invalid_event_id")
    return event


class BillingStore:
    """Idempotent merchant event ledger; no secrets, emails, or card information."""
    def __init__(self, path: str):
        target = Path(path)
        if not target.is_absolute() or not target.parent.is_dir():
            raise BillingError("absolute_existing_private_db_directory_required")
        self.path = str(target)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS stripe_events (
                    event_id TEXT PRIMARY KEY, kind TEXT NOT NULL, created INTEGER NOT NULL,
                    processed INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS stripe_subscriptions (
                    subscription_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL,
                    status TEXT NOT NULL, period_end INTEGER, event_created INTEGER NOT NULL);
            """)
        os.chmod(self.path, 0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("PRAGMA busy_timeout=5000")
        return db

    def accept(self, event: dict) -> str:
        eid, kind = event.get("id"), event.get("type")
        if not isinstance(eid, str) or not IDENTIFIER.fullmatch(eid):
            raise BillingError("invalid_event_id")
        if kind not in EVENT_TYPES:
            raise BillingError("unsupported_event")
        obj = event.get("data", {}).get("object")
        if not isinstance(obj, dict):
            raise BillingError("missing_event_object")
        created = event.get("created")
        if not isinstance(created, int) or created < 0:
            raise BillingError("invalid_event_time")
        if kind.startswith("customer.subscription."):
            sid, customer, status = obj.get("id"), obj.get("customer"), obj.get("status")
            if not all(isinstance(x, str) and IDENTIFIER.fullmatch(x)
                       for x in (sid, customer)):
                raise BillingError("invalid_subscription_identity")
            if kind.endswith("deleted"):
                status = "canceled"
            if status not in VALID_STATUSES:
                raise BillingError("invalid_subscription_status")
            # Stripe API v2025+ stores period_end on subscription items.
            items = obj.get("items", {}).get("data", []) if isinstance(obj.get("items"), dict) else []
            period_end = obj.get("current_period_end")
            if items and isinstance(items[0], dict):
                period_end = items[0].get("current_period_end", period_end)
            if not isinstance(period_end, int):
                period_end = None
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute(
                "INSERT OR IGNORE INTO stripe_events VALUES(?,?,?,?)",
                (eid, kind, created, int(time.time())))
            if cursor.rowcount == 0:
                return "duplicate"
            if kind.startswith("customer.subscription."):
                db.execute("""
                    INSERT INTO stripe_subscriptions VALUES(?,?,?,?,?)
                    ON CONFLICT(subscription_id) DO UPDATE SET
                      customer_id=excluded.customer_id,
                      status=excluded.status,
                      period_end=excluded.period_end,
                      event_created=excluded.event_created
                    WHERE excluded.event_created >= stripe_subscriptions.event_created
                    """, (sid, customer, status, period_end, created))
        return "recorded"


def list_merchant_subscriptions(api_key: str, *, max_pages=10) -> list[dict]:
    """Read-only Stripe merchant subscriptions. Never enumerate other merchants."""
    if not api_key.startswith(("sk_test_", "sk_live_")):
        raise BillingError("server_side_stripe_key_required")
    output = []
    cursor = None
    for _ in range(max_pages):
        params = {"limit": "100", "status": "all"}
        if cursor:
            params["starting_after"] = cursor
        url = "https://api.stripe.com/v1/subscriptions?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + api_key, "Accept": "application/json"}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                raw = response.read(1_000_001)
        except Exception:
            raise BillingError("stripe_read_failed") from None
        if len(raw) > 1_000_000:
            raise BillingError("response_too_large")
        data = json.loads(raw)
        page = data.get("data") if isinstance(data, dict) else None
        if not isinstance(page, list):
            raise BillingError("invalid_stripe_response")
        for item in page:
            if isinstance(item, dict):
                output.append({k: item.get(k) for k in
                               ("id", "status", "currency", "customer", "cancel_at_period_end")})
        if not data.get("has_more"):
            return output
        if not page or not isinstance(page[-1].get("id"), str):
            raise BillingError("pagination_invalid")
        cursor = page[-1]["id"]
    raise BillingError("pagination_limit_exceeded")


class WebhookHandler(BaseHTTPRequestHandler):
    """Mount at /webhooks/stripe behind authenticated TLS reverse proxy."""
    def do_POST(self):
        if self.path != "/webhooks/stripe":
            return self._reply(404)
        secret, path = os.getenv("STRIPE_WEBHOOK_SECRET", ""), os.getenv("STRIPE_EVENTS_DB", "")
        if not secret or not path:
            return self._reply(503)
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            return self._reply(400)
        if not 0 <= length <= MAX_BODY:
            return self._reply(413)
        raw = self.rfile.read(length)
        try:
            event = verify_stripe_signature(raw, self.headers.get("Stripe-Signature", ""), secret)
            BillingStore(path).accept(event)
        except BillingError:
            return self._reply(400)
        except (OSError, sqlite3.Error):
            return self._reply(503)
        self._reply(200)

    def _reply(self, status):
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *_):
        pass  # Never log webhook signature, payload, or raw payment metadata.


def run():
    if not os.getenv("STRIPE_WEBHOOK_SECRET", "").startswith("whsec_"):
        raise SystemExit("STRIPE_WEBHOOK_SECRET is required")
    if not os.getenv("STRIPE_EVENTS_DB", ""):
        raise SystemExit("STRIPE_EVENTS_DB is required")
    BillingStore(os.environ["STRIPE_EVENTS_DB"])
    host = os.getenv("STRIPE_BIND", "127.0.0.1")
    if host not in ("127.0.0.1", "::1"):
        raise SystemExit("Bind loopback and use a trusted TLS reverse proxy")
    ThreadingHTTPServer((host, int(os.getenv("STRIPE_PORT", "8091"))), WebhookHandler).serve_forever()


if __name__ == "__main__":
    run()