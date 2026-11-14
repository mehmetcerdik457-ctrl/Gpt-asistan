"""Read-only Google Play voided-order reconciliation; no entitlement mutation.

A subscription purchase token can cover multiple renewal orders. We dedupe on
the Google order ID, not token, and NEVER revoke an entire subscription merely
because one order appeared in Voided Purchases. This is an audit-only candidate.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing

from server.play_google_api import PACKAGE, TOKEN_RE

API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
MAX_PAGE_BYTES = 1024 * 1024
MAX_PAGES = 5
MAX_RESULTS = 1000
THIRTY_DAYS_MS = 30 * 24 * 3600 * 1000
ORDER_RE = re.compile(r"^[A-Za-z0-9_.-]{1,240}$")
PAGE_RE = re.compile(r"^[A-Za-z0-9_~.+=/-]{1,1024}$")


class VoidedAuditUnavailable(RuntimeError):
    """Redacted failure: contains no order, purchase or credential detail."""


def initialize_voided_orders(db: sqlite3.Connection) -> None:
    """Migration by trusted operator, NOT called on public request path."""
    db.execute("""CREATE TABLE IF NOT EXISTS play_voided_orders_audit (
        order_sha256 TEXT PRIMARY KEY,
        purchase_token_sha256 TEXT NOT NULL,
        voided_at_ms INTEGER NOT NULL,
        reason INTEGER NOT NULL,
        recorded_at_ms INTEGER NOT NULL
    )""")
    db.commit()


class VoidedOrderAuditor:
    def __init__(self, *, oauth_supplier, db_factory, enabled=None,
                 opener=None, clock=None):
        if not callable(oauth_supplier) or not callable(db_factory):
            raise ValueError("VOIDED_AUDIT_NOT_PROVISIONED")
        self._oauth = oauth_supplier
        self._db_factory = db_factory
        self._enabled = enabled or (
            lambda: os.getenv("ORBA_PLAY_VOIDED_AUDIT_ENABLED") == "YES")
        self._opener = opener or urllib.request.urlopen
        self._clock = clock or time.time
        if not callable(self._enabled) or not callable(self._clock):
            raise ValueError("VOIDED_AUDIT_CONFIG_INVALID")

    def _get_page(self, *, access_token, start_ms, end_ms, page_token=None):
        params = {
            "type": "1",  # includes subscriptions; default type=0 omits them!
            "maxResults": str(MAX_RESULTS),
            "startTime": str(start_ms),
            "endTime": str(end_ms),
        }
        if page_token is not None:
            params["token"] = page_token
        package = urllib.parse.quote(PACKAGE, safe="")
        url = f"{API}/{package}/purchases/voidedpurchases?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + access_token,
            "Accept": "application/json",
        }, method="GET")
        try:
            with self._opener(request, timeout=8) as response:
                if getattr(response, "status", 200) != 200:
                    raise VoidedAuditUnavailable("VOIDED_PROVIDER_UNAVAILABLE")
                raw = response.read(MAX_PAGE_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, OSError):
            raise VoidedAuditUnavailable("VOIDED_PROVIDER_UNAVAILABLE") from None
        if len(raw) > MAX_PAGE_BYTES:
            raise VoidedAuditUnavailable("VOIDED_RESPONSE_INVALID")
        try:
            data = json.loads(raw)
            rows = data["voidedPurchases"]
            if not isinstance(rows, list) or len(rows) > MAX_RESULTS:
                raise ValueError()
            pagination = data.get("tokenPagination", {})
            if not isinstance(pagination, dict):
                raise ValueError()
            next_token = pagination.get("nextPageToken")
            if next_token is not None and (
                not isinstance(next_token, str) or
                not PAGE_RE.fullmatch(next_token)):
                raise ValueError()
            return rows, next_token
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise VoidedAuditUnavailable("VOIDED_RESPONSE_INVALID") from None

    @staticmethod
    def _validate(row):
        if not isinstance(row, dict):
            raise VoidedAuditUnavailable("VOIDED_RECORD_INVALID")
        order = row.get("orderId")
        purchase = row.get("purchaseToken")
        when = row.get("voidedTimeMillis")
        reason = row.get("voidedReason")
        if (not isinstance(order, str) or not ORDER_RE.fullmatch(order) or
            not isinstance(purchase, str) or not TOKEN_RE.fullmatch(purchase) or
            not isinstance(when, str) or
            not re.fullmatch(r"[0-9]{1,17}", when) or
            type(reason) not in (str, int) or
            not re.fullmatch(r"[0-8]", str(reason)) or
            int(when) <= 0):
            raise VoidedAuditUnavailable("VOIDED_RECORD_INVALID")
        return (hashlib.sha256(order.encode()).hexdigest(),
                hashlib.sha256(purchase.encode()).hexdigest(),
                int(when), int(reason))

    def reconcile(self, *, start_ms=None, end_ms=None):
        """Audit a bounded window, atomically; no grants/refunds/revocations.

        A complete window is validated before any DB write. If pagination is
        truncated or provider/DB fails, the transaction is not committed.
        """
        if self._enabled() is not True:
            raise VoidedAuditUnavailable("VOIDED_AUDIT_DISABLED")
        try:
            now_ms = int(self._clock() * 1000)
            if start_ms is None:
                start_ms = now_ms - 48 * 3600 * 1000
            if end_ms is None:
                end_ms = now_ms
            if (type(start_ms) is not int or type(end_ms) is not int or
                not now_ms > 0 or not 0 <= start_ms < end_ms <= now_ms or
                start_ms < now_ms - THIRTY_DAYS_MS):
                raise VoidedAuditUnavailable("VOIDED_WINDOW_INVALID")
            token = self._oauth()
            if (not isinstance(token, str) or
                not 1 <= len(token) <= 8192 or
                not token.isascii() or
                any(c.isspace() or ord(c) < 33 or ord(c) >= 127 for c in token)):
                raise VoidedAuditUnavailable("VOIDED_OAUTH_UNAVAILABLE")
            entries = {}
            page, seen_tokens = None, set()
            pages = 0
            while True:
                if pages >= MAX_PAGES:
                    raise VoidedAuditUnavailable("VOIDED_PAGINATION_LIMIT")
                rows, next_page = self._get_page(
                    access_token=token, start_ms=start_ms,
                    end_ms=end_ms, page_token=page)
                pages += 1
                for row in rows:
                    order_hash, purchase_hash, when, reason = self._validate(row)
                    value = (purchase_hash, when, reason)
                    old = entries.get(order_hash)
                    if old is not None and old != value:
                        raise VoidedAuditUnavailable("VOIDED_ORDER_CONFLICT")
                    entries[order_hash] = value
                if next_page is None:
                    break
                if next_page in seen_tokens:
                    raise VoidedAuditUnavailable("VOIDED_PAGINATION_CYCLE")
                seen_tokens.add(next_page)
                page = next_page
            added = 0
            with closing(self._db_factory()) as db:
                try:
                    db.execute("BEGIN IMMEDIATE")
                    for order_hash, (purchase_hash, when, reason) in entries.items():
                        before = db.execute(
                            "SELECT purchase_token_sha256, voided_at_ms, reason "
                            "FROM play_voided_orders_audit WHERE order_sha256=?",
                            (order_hash,)).fetchone()
                        if before is not None:
                            valid = (
                                hmac.compare_digest(before[0], purchase_hash) and
                                before[1] == when and before[2] == reason)
                            if not valid:
                                raise VoidedAuditUnavailable("VOIDED_ORDER_CONFLICT")
                            continue
                        db.execute(
                            "INSERT INTO play_voided_orders_audit "
                            "(order_sha256,purchase_token_sha256,voided_at_ms,reason,recorded_at_ms) "
                            "VALUES(?,?,?,?,?)",
                            (order_hash, purchase_hash, when, reason, now_ms))
                        added += 1
                    db.commit()
                except BaseException:
                    db.rollback()
                    raise
            return {"pages": pages, "observed_orders": len(entries),
                    "new_orders": added, "entitlement_changed": False}
        except VoidedAuditUnavailable:
            raise
        except Exception:
            raise VoidedAuditUnavailable("VOIDED_AUDIT_UNAVAILABLE") from None
