"""ORBA Play RTDN: Google OIDC authenticated Pub/Sub push audit.

RTDN is a CHANGED-STATE signal, not proof of entitlement. No entitlement
table updates, purchase acknowledgement, or merchant actions occur here.
"""
import base64
import binascii
import hashlib
import hmac
import json
import re
import sqlite3
import time
from dataclasses import replace
from contextlib import closing
from server.play_account_id import obfuscated_play_account_id
from server.play_entitlement_gate import PACKAGE, token_digest
from server.play_google_api import TOKEN_RE, get_subscription_v2
from server.play_subscription_mapper import map_verified_subscription

ENDPOINT = "/api/v1/play/rtdn"
MAX_BODY = 16384
ISSUERS = frozenset(("accounts.google.com", "https://accounts.google.com"))


class RtdnDenied(ValueError):
    """Non-sensitive client/auth denial."""


class RtdnRetry(RuntimeError):
    """Provider or persistent store unavailable; Pub/Sub should redeliver."""


def verify_google_oidc(token, audience):
    """Production verifier checks Google signature, audience and expiry."""
    from google.oauth2 import id_token
    from google.auth.transport import requests
    return id_token.verify_oauth2_token(token, requests.Request(), audience=audience)


def initialize_rtdn(db):
    """Trusted installer migration only; never called from HTTP handler."""
    db.execute("""CREATE TABLE IF NOT EXISTS play_rtdn_audit (
        message_digest TEXT PRIMARY KEY,
        payload_digest TEXT NOT NULL,
        purchase_token_digest TEXT,
        outcome TEXT NOT NULL CHECK(outcome IN (
            'TEST', 'RECHECKED_BOUND', 'RECHECKED_UNBOUND')),
        recorded_at_ms INTEGER NOT NULL
    )""")
    db.commit()


class PlayRtdnProcessor:
    def __init__(self, *, audience, service_account_email, subscription,
                 allowed_products, server_secret, db_factory, oauth_supplier,
                 verifier=None, provider_opener=None, clock=None,
                 snapshot_recorder=None):
        if not isinstance(audience, str) or not re.fullmatch(r"https://[^\s]{1,400}", audience):
            raise ValueError("RTDN_AUDIENCE_MISSING")
        if not isinstance(service_account_email, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]{1,128}@[A-Za-z0-9_.-]+\.iam\.gserviceaccount\.com",
            service_account_email):
            raise ValueError("RTDN_SERVICE_EMAIL_MISSING")
        if not isinstance(subscription, str) or not re.fullmatch(
            r"projects/[A-Za-z0-9_.~+%-]{1,128}/subscriptions/[A-Za-z0-9_.~+%-]{1,128}",
            subscription):
            raise ValueError("RTDN_SUBSCRIPTION_MISSING")
        if not isinstance(server_secret, bytes) or len(server_secret) < 32:
            raise ValueError("RTDN_SECRET_MISSING")
        if (not isinstance(allowed_products, (set, frozenset)) or not allowed_products or
            any(not isinstance(x, str) or not re.fullmatch(r"[A-Za-z0-9_.]{1,100}", x)
                for x in allowed_products)):
            raise ValueError("RTDN_PRODUCTS_MISSING")
        if not callable(db_factory) or not callable(oauth_supplier):
            raise ValueError("RTDN_DEPENDENCIES_MISSING")
        if verifier is not None and not callable(verifier):
            raise ValueError("RTDN_VERIFIER_INVALID")
        if snapshot_recorder is not None and not callable(snapshot_recorder):
            raise ValueError("RTDN_SNAPSHOT_RECORDER_INVALID")
        self.audience = audience
        self.service_account_email = service_account_email
        self.subscription = subscription
        self.allowed_products = frozenset(allowed_products)
        self.server_secret = server_secret
        self.db_factory = db_factory
        self.oauth_supplier = oauth_supplier
        self.verifier = verifier or verify_google_oidc
        self.provider_opener = provider_opener
        self.clock = clock or time.time
        # No migration or snapshot writes unless explicitly installed.
        self.snapshot_recorder = snapshot_recorder

    def authenticate(self, authorization):
        if (not isinstance(authorization, str) or not authorization.startswith("Bearer ") or
            not re.fullmatch(r"[A-Za-z0-9_.-]{8,8192}", authorization[7:])):
            raise RtdnDenied("RTDN_AUTH_DENIED")
        try:
            claims = self.verifier(authorization[7:], self.audience)
        except Exception:
            raise RtdnDenied("RTDN_AUTH_DENIED") from None
        if (not isinstance(claims, dict) or
            claims.get("iss") not in ISSUERS or
            claims.get("aud") != self.audience or
            claims.get("email") != self.service_account_email or
            claims.get("email_verified") not in (True, "true") or
            type(claims.get("iat")) is not int or
            type(claims.get("exp")) is not int):
            raise RtdnDenied("RTDN_AUTH_DENIED")
        now = int(self.clock())
        if not claims["iat"] <= now < claims["exp"] or claims["iat"] < now - 3600:
            raise RtdnDenied("RTDN_AUTH_DENIED")

    def unpack(self, raw):
        if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BODY:
            raise RtdnDenied("RTDN_PAYLOAD_INVALID")
        try:
            envelope = json.loads(raw)
            if not isinstance(envelope, dict) or envelope.get("subscription") != self.subscription:
                raise ValueError()
            msg = envelope["message"]
            message_id = msg.get("messageId", msg.get("message_id"))
            if not isinstance(message_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", message_id):
                raise ValueError()
            data = base64.b64decode(msg["data"], validate=True)
            if not 0 < len(data) <= MAX_BODY:
                raise ValueError()
            event = json.loads(data)
            if (not isinstance(event, dict) or event.get("version") != "1.0" or
                event.get("packageName") != PACKAGE or
                not isinstance(event.get("eventTimeMillis"), str) or
                not re.fullmatch(r"[0-9]{1,17}", event["eventTimeMillis"])):
                raise ValueError()
            if "testNotification" in event:
                if (not isinstance(event["testNotification"], dict) or
                    event["testNotification"].get("version") != "1.0" or
                    "subscriptionNotification" in event):
                    raise ValueError()
                return message_id, data, None, True
            n = event["subscriptionNotification"]
            if (not isinstance(n, dict) or n.get("version") != "1.0" or
                type(n.get("notificationType")) is not int or
                not 1 <= n["notificationType"] <= 99):
                raise ValueError()
            token = n["purchaseToken"]
            if not isinstance(token, str) or len(token) > 4096 or not TOKEN_RE.fullmatch(token):
                raise ValueError()
            return message_id, data, token, False
        except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, binascii.Error):
            raise RtdnDenied("RTDN_PAYLOAD_INVALID") from None

    def process(self, *, authorization, raw):
        """Audit RTDN; optionally refresh a *non-authoritative* snapshot.

        A stale/canceled/expired RTDN never determines the recorded state:
        only fresh owner-bound Play Developer API data does. A failed snapshot
        write leads to a Pub/Sub retry without acknowledging the RTDN in audit.
        """
        self.authenticate(authorization)
        message_id, payload, purchase_token, is_test = self.unpack(raw)
        msg_hash = hashlib.sha256(message_id.encode("utf-8")).hexdigest()
        payload_hash = hashlib.sha256(payload).hexdigest()
        try:
            with closing(self.db_factory()) as db:
                def previous():
                    return db.execute(
                        "SELECT payload_digest FROM play_rtdn_audit WHERE message_digest=?",
                        (msg_hash,)).fetchone()
                old = previous()
                if old:
                    if not hmac.compare_digest(old[0], payload_hash):
                        raise RtdnDenied("RTDN_MESSAGE_ID_CONFLICT")
                    return False
                token_hash, outcome = None, "TEST"
                if not is_test:
                    # Observation order is when *server-side fetch starts*.
                    # A delayed response must not overwrite a later-started
                    # verification of the same purchase in the snapshot ledger.
                    checked_at_ms = int(self.clock() * 1000)
                    token_hash = token_digest(purchase_token)
                    owner = db.execute(
                        "SELECT owner_id FROM play_token_owners WHERE token_sha256=?",
                        (token_hash,)).fetchone()
                    try:
                        access_token = self.oauth_supplier()
                        if (not isinstance(access_token, str) or not 1 <= len(access_token) <= 8192 or
                            any(c.isspace() or ord(c) < 33 for c in access_token)):
                            raise ValueError()
                        provider = get_subscription_v2(
                            purchase_token, access_token, opener=self.provider_opener)
                        if not any(x["productId"] in self.allowed_products for x in provider["lineItems"]):
                            raise ValueError()
                        outcome = "RECHECKED_UNBOUND"
                        if owner:
                            identifiers = provider.get("externalAccountIdentifiers")
                            actual = identifiers.get("obfuscatedExternalAccountId") if isinstance(identifiers, dict) else None
                            expected = obfuscated_play_account_id(
                                authenticated_owner_id=owner[0], server_secret=self.server_secret)
                            if not isinstance(actual, str) or not hmac.compare_digest(actual, expected):
                                raise ValueError()
                            outcome = "RECHECKED_BOUND"
                            if self.snapshot_recorder is not None:
                                # For now require exactly ONE permitted item.
                                # Bundles must not be partially snapshotted.
                                eligible = [
                                    item.get("productId")
                                    for item in provider["lineItems"]
                                    if item.get("productId") in self.allowed_products
                                ]
                                if len(eligible) != 1:
                                    raise ValueError()
                                # map_verified_subscription alone deliberately
                                # sets verified=False. Only the *trusted fresh
                                # get_subscription_v2 response above* and owner
                                # HMAC comparison authorize marking provenance.
                                mapped = map_verified_subscription(
                                    provider, purchase_token=purchase_token,
                                    owner_id=owner[0], product_id=eligible[0])
                                self.snapshot_recorder(
                                    db, replace(mapped, verified_by_google_api=True),
                                    server_secret=self.server_secret,
                                    observed_at_ms=checked_at_ms)
                                # This writes diagnostic state ONLY. The RTDN
                                # never returns paid access or alters entitlements.
                    except Exception:
                        raise RtdnRetry("RTDN_PROVIDER_RECHECK_UNAVAILABLE") from None
                with db:
                    cursor = db.execute(
                        "INSERT OR IGNORE INTO play_rtdn_audit "
                        "(message_digest,payload_digest,purchase_token_digest,outcome,recorded_at_ms) "
                        "VALUES(?,?,?,?,?)",
                        (msg_hash, payload_hash, token_hash, outcome, int(self.clock() * 1000)))
                saved = previous()
                if not saved or not hmac.compare_digest(saved[0], payload_hash):
                    raise RtdnDenied("RTDN_MESSAGE_ID_CONFLICT")
                return cursor.rowcount == 1
        except (RtdnDenied, RtdnRetry):
            raise
        except (sqlite3.Error, OSError, ValueError, TypeError):
            raise RtdnRetry("RTDN_STORE_UNAVAILABLE") from None
