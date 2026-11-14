"""Offline Google Play RTDN -> provider-verified diagnostic snapshot regressions.

All provider/OIDC responses synthetic; no credentials or real subscriptions.
"""
import hashlib
import sqlite3
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone

from server.play_rtdn import (
    PlayRtdnProcessor, RtdnRetry, RtdnDenied, initialize_rtdn
)
from server.play_verified_snapshot import (
    initialize_snapshot, record_verified_snapshot, diagnostic_snapshot
)
from server.play_owner_binding import (
    initialize as initialize_owners, bind_or_verify_owner
)
from server.play_entitlement_gate import PACKAGE, VerifiedPlayPurchase, token_digest
from server.tests.test_play_rtdn import (
    NOW, AUDIENCE, EMAIL, SUB, PRODUCT, JWT, claims, event, wrapped
)
from server.tests.test_play_acknowledgement_service import FakeGoogle, purchase, SECRET


class RtdnSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dbpath = self.tmp.name + "/private.sqlite3"
        with sqlite3.connect(self.dbpath) as db:
            initialize_owners(db)
            initialize_rtdn(db)
            initialize_snapshot(db)
        self.now = [NOW]
        self.google = FakeGoogle(purchase(
            owner="alice", ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        self.oauth_calls = 0
        def oauth():
            self.oauth_calls += 1
            return "offline-play-oauth"
        self.processor = PlayRtdnProcessor(
            audience=AUDIENCE, service_account_email=EMAIL,
            subscription=SUB, allowed_products={PRODUCT},
            server_secret=SECRET,
            db_factory=lambda: sqlite3.connect(self.dbpath),
            oauth_supplier=oauth,
            verifier=lambda token, audience: claims(),
            provider_opener=lambda request, timeout: self.google(request, timeout),
            clock=lambda: self.now[0],
            snapshot_recorder=record_verified_snapshot,
        )

    def bind(self, owner="alice"):
        with sqlite3.connect(self.dbpath) as db:
            bind_or_verify_owner(db, purchase_token="token-one",
                authenticated_owner_id=owner, now_ms=NOW * 1000)

    def push(self, msgid="msg-1", notice=None):
        return self.processor.process(
            authorization="Bearer " + JWT,
            raw=wrapped(msgid=msgid, data=notice))

    def snapshot(self, owner="alice"):
        with sqlite3.connect(self.dbpath) as db:
            return diagnostic_snapshot(
                db,owner_id=owner,purchase_token="token-one",
                product_id=PRODUCT,server_secret=SECRET,
                now_ms=int(self.now[0] * 1000))

    def row_counts(self):
        with sqlite3.connect(self.dbpath) as db:
            return (
                db.execute("SELECT COUNT(*) FROM play_rtdn_audit").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM play_verified_snapshots").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM play_token_owners").fetchone()[0],
            )

    def test_bound_owner_refreshes_active_diagnostic_from_one_fresh_get(self):
        self.bind()
        self.assertTrue(self.push())
        snapshot=self.snapshot()
        self.assertEqual(snapshot["last_provider_state"], "SUBSCRIPTION_STATE_ACTIVE")
        self.assertTrue(snapshot["historically_allowed_at_check"])
        self.assertTrue(snapshot["requires_live_google_verification"])
        self.assertEqual(self.row_counts(),(1,1,1))
        self.assertEqual([x[0] for x in self.google.requests],["GET"])

    def test_unbound_token_audited_but_never_registered_as_owner(self):
        self.assertTrue(self.push())
        self.assertEqual(self.row_counts(),(1,0,0))
        self.assertIsNone(self.snapshot())

    def test_test_notification_never_reads_google_or_records_snapshot(self):
        self.bind()
        self.assertTrue(self.push(notice=event(is_test=True)))
        self.assertEqual(self.row_counts(),(1,0,1))
        self.assertEqual(self.google.requests,[])
        self.assertEqual(self.oauth_calls,0)

    def test_stale_canceled_signal_cannot_override_current_active_provider(self):
        self.bind()
        self.assertTrue(self.push(notice=event(kind=3)))
        self.assertEqual(self.snapshot()["last_provider_state"],
                         "SUBSCRIPTION_STATE_ACTIVE")

    def test_renewed_signal_with_provider_on_hold_records_denied(self):
        self.bind()
        self.google=FakeGoogle(purchase(owner="alice",
            state="SUBSCRIPTION_STATE_ON_HOLD",
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        self.assertTrue(self.push(notice=event(kind=2)))
        self.assertEqual(self.snapshot()["last_provider_state"],
                         "SUBSCRIPTION_STATE_ON_HOLD")
        self.assertFalse(self.snapshot()["historically_allowed_at_check"])

    def test_expired_signal_with_provider_grace_records_grace_not_expired(self):
        self.bind()
        self.google=FakeGoogle(purchase(owner="alice",
            state="SUBSCRIPTION_STATE_IN_GRACE_PERIOD",
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        self.assertTrue(self.push(notice=event(kind=13)))
        self.assertEqual(self.snapshot()["last_provider_state"],
                         "SUBSCRIPTION_STATE_IN_GRACE_PERIOD")
        self.assertTrue(self.snapshot()["historically_allowed_at_check"])

    def test_second_newer_check_overwrites_active_to_hold(self):
        self.bind()
        self.assertTrue(self.push(msgid="msg-1"))
        self.now[0] += 1
        self.google=FakeGoogle(purchase(owner="alice",
            state="SUBSCRIPTION_STATE_ON_HOLD",
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        self.assertTrue(self.push(msgid="msg-2",notice=event(kind=2)))
        self.assertEqual(self.snapshot()["last_provider_state"],
                         "SUBSCRIPTION_STATE_ON_HOLD")
        self.assertEqual(self.row_counts(),(2,1,1))

    def test_replayed_same_message_does_not_call_provider_again(self):
        self.bind()
        self.assertTrue(self.push())
        self.google=FakeGoogle(purchase(owner="alice",
            state="SUBSCRIPTION_STATE_ON_HOLD",
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        self.assertFalse(self.push())
        self.assertEqual(len(self.google.requests),0)
        self.assertEqual(self.snapshot()["last_provider_state"],
                         "SUBSCRIPTION_STATE_ACTIVE")

    def test_old_event_timestamp_ignored_in_favor_of_fresh_provider_state(self):
        self.bind()
        stale=event(kind=2)
        stale["eventTimeMillis"]="1577836800000"
        self.google=FakeGoogle(purchase(owner="alice",
            state="SUBSCRIPTION_STATE_EXPIRED",
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        self.assertTrue(self.push(notice=stale))
        self.assertEqual(self.snapshot()["last_provider_state"],
                         "SUBSCRIPTION_STATE_EXPIRED")
        self.assertFalse(self.snapshot()["historically_allowed_at_check"])

    def test_missing_snapshot_migration_returns_retry_and_no_rtdn_ack(self):
        self.bind()
        with sqlite3.connect(self.dbpath) as db:
            db.execute("DROP TABLE play_verified_snapshots")
        with self.assertRaises(RtdnRetry):
            self.push()
        with sqlite3.connect(self.dbpath) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM play_rtdn_audit").fetchone()[0],0)

    def test_recorder_exception_redacted_and_no_success_ack(self):
        self.bind()
        def failing(*args, **kwargs):
            raise RuntimeError("PRIVATE_DB_SECRET_PATH")
        self.processor.snapshot_recorder=failing
        with self.assertRaises(RtdnRetry) as ctx:
            self.push()
        self.assertNotIn("PRIVATE_DB_SECRET_PATH",str(ctx.exception))
        self.assertEqual(self.row_counts(),(0,0,1))

    def test_wrong_owner_hmac_denied_before_snapshot(self):
        self.bind(owner="alice")
        self.google=FakeGoogle(purchase(owner="bob",
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        with self.assertRaises(RtdnRetry):
            self.push()
        self.assertEqual(self.row_counts(),(0,0,1))

    def test_pending_ack_observed_as_denied_without_ack_post(self):
        self.bind()
        self.google=FakeGoogle(purchase(owner="alice"))
        self.assertTrue(self.push())
        self.assertFalse(self.snapshot()["historically_allowed_at_check"])
        self.assertEqual([x[0] for x in self.google.requests],["GET"])

    def test_expired_expiry_with_active_state_still_denied(self):
        self.bind()
        self.google=FakeGoogle(purchase(owner="alice",expiry="2020-01-01T00:00:00Z",
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        self.assertTrue(self.push())
        self.assertFalse(self.snapshot()["historically_allowed_at_check"])
        self.assertTrue(self.snapshot()["expired_at_query"])

    def test_unknown_product_with_bound_token_retries_and_no_snapshot(self):
        self.bind()
        self.google=FakeGoogle(purchase(owner="alice",product="wrong",
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        with self.assertRaises(RtdnRetry):
            self.push()
        self.assertEqual(self.row_counts(),(0,0,1))

    def test_multiple_allowed_products_rejected_to_avoid_partial_updates(self):
        self.bind()
        self.processor.allowed_products=frozenset({PRODUCT,"orba_pro_yearly"})
        item=purchase(owner="alice",
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED")
        item["lineItems"].append({
            "productId":"orba_pro_yearly",
            "expiryTime":"2027-01-01T00:00:00Z"})
        self.google=FakeGoogle(item)
        with self.assertRaises(RtdnRetry):
            self.push()
        self.assertEqual(self.row_counts(),(0,0,1))

    def test_snapshot_cannot_read_other_owner_record(self):
        self.bind()
        self.push()
        self.assertIsNone(self.snapshot(owner="mallory"))

    def test_old_inflight_fetch_does_not_replace_newer_hold(self):
        self.bind()
        verified=VerifiedPlayPurchase(
            package_name=PACKAGE, product_id=PRODUCT,
            purchase_token_sha256=token_digest("token-one"),
            owner_id="alice",expires_at_ms=NOW*1000+100000,
            subscription_state="SUBSCRIPTION_STATE_ON_HOLD",
            acknowledged=True,verified_by_google_api=True)
        with sqlite3.connect(self.dbpath) as db:
            record_verified_snapshot(
                db,verified,server_secret=SECRET,
                observed_at_ms=NOW*1000+2000)
        self.assertTrue(self.push(msgid="older-inflight"))
        self.assertEqual(self.snapshot()["last_provider_state"],
                         "SUBSCRIPTION_STATE_ON_HOLD")
        self.assertEqual(self.row_counts(),(1,1,1))

    def test_same_timestamp_conflict_is_retryable_no_success_ack(self):
        self.bind()
        verified=VerifiedPlayPurchase(
            package_name=PACKAGE,product_id=PRODUCT,
            purchase_token_sha256=token_digest("token-one"),
            owner_id="alice",expires_at_ms=NOW*1000+100000,
            subscription_state="SUBSCRIPTION_STATE_ON_HOLD",
            acknowledged=True,verified_by_google_api=True)
        with sqlite3.connect(self.dbpath) as db:
            record_verified_snapshot(db,verified,server_secret=SECRET,
                                     observed_at_ms=NOW*1000)
        with self.assertRaises(RtdnRetry):
            self.push()
        self.assertEqual(self.row_counts(),(0,1,1))
        self.assertEqual(self.snapshot()["last_provider_state"],
                         "SUBSCRIPTION_STATE_ON_HOLD")

    def test_provider_outage_does_not_update_snapshot(self):
        self.bind()
        self.google=FakeGoogle(urllib.error.URLError("network-offline"))
        with self.assertRaises(RtdnRetry):
            self.push()
        self.assertEqual(self.row_counts(),(0,0,1))

    def test_injected_non_callable_recorder_denied(self):
        with self.assertRaises(ValueError):
            PlayRtdnProcessor(
                audience=AUDIENCE,service_account_email=EMAIL,
                subscription=SUB,allowed_products={PRODUCT},
                server_secret=SECRET,db_factory=lambda: None,
                oauth_supplier=lambda:"x",snapshot_recorder=True)


if __name__=="__main__":
    unittest.main()
