"""Durable Play snapshot proofs: no provider fetch or user entitlement from cache."""
import os
import sqlite3
import tempfile
import unittest
import urllib.error
from dataclasses import replace

from server.play_entitlement_gate import PACKAGE, VerifiedPlayPurchase, token_digest
from server.play_verified_snapshot import (
    SnapshotRejected, initialize_snapshot, record_verified_snapshot,
    diagnostic_snapshot,
)
from server.play_owner_binding import initialize as initialize_owners
from server.play_acknowledgement_service import acknowledge_then_verify_subscription
from server.play_gateway_boundary import PlayGatewayBoundary, PlayBoundaryError
from server.tests.test_play_acknowledgement_service import (
    FakeGoogle, purchase, SECRET, NOW, PRODUCT,
)


class SnapshotStorageTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        initialize_snapshot(self.db)

    def tearDown(self):
        self.db.close()

    def p(self, *, owner="alice", state="SUBSCRIPTION_STATE_ACTIVE",
          acknowledged=True, verified=True, product=PRODUCT,
          expiry=NOW + 100000, token="token-1"):
        return VerifiedPlayPurchase(
            package_name=PACKAGE, product_id=product,
            purchase_token_sha256=token_digest(token), owner_id=owner,
            expires_at_ms=expiry, subscription_state=state,
            acknowledged=acknowledged, verified_by_google_api=verified)

    def record(self, p=None, at=NOW):
        return record_verified_snapshot(
            self.db, p if p is not None else self.p(),
            server_secret=SECRET, observed_at_ms=at)

    def status(self, *, owner="alice", token="token-1", now=NOW):
        return diagnostic_snapshot(
            self.db, owner_id=owner, purchase_token=token,
            product_id=PRODUCT, server_secret=SECRET, now_ms=now)

    def test_initial_trusted_positive_recorded(self):
        self.assertTrue(self.record())
        s = self.status()
        self.assertEqual(s["last_provider_state"], "SUBSCRIPTION_STATE_ACTIVE")
        self.assertTrue(s["historically_allowed_at_check"])
        self.assertTrue(s["requires_live_google_verification"])

    def test_cache_is_never_an_entitlement_api(self):
        self.record()
        s = self.status()
        self.assertNotIn("entitled", s)
        self.assertNotIn("grant", s)
        self.assertTrue(s["requires_live_google_verification"])

    def test_no_plaintext_owner_or_purchase_token_on_disk(self):
        self.record()
        raw = str(self.db.execute(
            "SELECT * FROM play_verified_snapshots").fetchall())
        self.assertNotIn("alice", raw)
        self.assertNotIn("token-1", raw)
        self.assertNotIn(SECRET.decode(), raw)

    def test_newer_hold_denies_and_replaces_active(self):
        self.record()
        self.assertTrue(self.record(
            self.p(state="SUBSCRIPTION_STATE_ON_HOLD"), at=NOW+1000))
        s = self.status(now=NOW+1000)
        self.assertEqual(s["last_provider_state"], "SUBSCRIPTION_STATE_ON_HOLD")
        self.assertFalse(s["historically_allowed_at_check"])

    def test_expired_subscriptions_stored_as_denied(self):
        self.record(self.p(expiry=NOW))
        s=self.status()
        self.assertFalse(s["historically_allowed_at_check"])
        self.assertTrue(s["expired_at_query"])

    def test_canceled_before_expiry_records_paid_time(self):
        self.record(self.p(state="SUBSCRIPTION_STATE_CANCELED"))
        self.assertTrue(self.status()["historically_allowed_at_check"])

    def test_grace_period_records_current_benefit(self):
        self.record(self.p(state="SUBSCRIPTION_STATE_IN_GRACE_PERIOD"))
        self.assertTrue(self.status()["historically_allowed_at_check"])

    def test_unacknowledged_is_not_historically_granted(self):
        self.record(self.p(acknowledged=False))
        self.assertFalse(self.status()["historically_allowed_at_check"])

    def test_older_success_cannot_regrant_newer_hold(self):
        self.record(self.p(state="SUBSCRIPTION_STATE_ON_HOLD"), at=NOW+1000)
        self.assertFalse(self.record(self.p(), at=NOW))
        self.assertEqual(self.status()["last_provider_state"],
                         "SUBSCRIPTION_STATE_ON_HOLD")

    def test_same_timestamp_identical_replay_idempotent(self):
        self.assertTrue(self.record())
        self.assertFalse(self.record())
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM play_verified_snapshots").fetchone()[0],1)

    def test_clock_tie_state_conflict_rejected_and_unchanged(self):
        self.record()
        with self.assertRaisesRegex(SnapshotRejected, "CLOCK_TIE_CONFLICT"):
            self.record(self.p(state="SUBSCRIPTION_STATE_EXPIRED"))
        self.assertEqual(self.status()["last_provider_state"],
                         "SUBSCRIPTION_STATE_ACTIVE")

    def test_cross_owner_cannot_replace_purchase_token(self):
        self.record()
        with self.assertRaisesRegex(SnapshotRejected,"OWNER_CONFLICT"):
            self.record(self.p(owner="bob"), at=NOW+1000)
        self.assertIsNone(self.status(owner="bob"))

    def test_wrong_owner_cannot_read_snapshot(self):
        self.record()
        self.assertIsNone(self.status(owner="bob"))

    def test_missing_purchase_token_not_visible(self):
        self.record()
        self.assertIsNone(self.status(token="unknown"))

    def test_wrong_product_has_independent_snapshot(self):
        self.record()
        another=self.p(product="orba_pro_yearly")
        self.assertTrue(self.record(another,at=NOW+1))
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM play_verified_snapshots").fetchone()[0],2)

    def test_unverified_dataclass_cannot_write(self):
        with self.assertRaisesRegex(SnapshotRejected, "PROVENANCE"):
            self.record(self.p(verified=False))
        self.assertIsNone(self.status())

    def test_raw_dict_cannot_write(self):
        with self.assertRaises(SnapshotRejected):
            self.record(self.p().__dict__)

    def test_invalid_package_cannot_write(self):
        with self.assertRaises(SnapshotRejected):
            self.record(replace(self.p(),package_name="attacker.package"))

    def test_bool_timestamp_denied(self):
        with self.assertRaises(SnapshotRejected):
            self.record(at=True)

    def test_bool_expiry_denied(self):
        with self.assertRaises(SnapshotRejected):
            self.record(self.p(expiry=True))

    def test_malformed_token_hash_denied(self):
        with self.assertRaises(SnapshotRejected):
            self.record(replace(self.p(),purchase_token_sha256="bad"))

    def test_missing_migration_does_not_auto_create(self):
        db=sqlite3.connect(":memory:")
        try:
            with self.assertRaises(sqlite3.OperationalError):
                record_verified_snapshot(db,self.p(),
                    server_secret=SECRET,observed_at_ms=NOW)
            found=db.execute("SELECT name FROM sqlite_master WHERE "
                "name='play_verified_snapshots'").fetchone()
            self.assertIsNone(found)
        finally:
            db.close()

    def test_status_after_expiry_still_non_authoritative(self):
        self.record(self.p(expiry=NOW+1))
        s=self.status(now=NOW+1)
        self.assertTrue(s["expired_at_query"])
        self.assertTrue(s["requires_live_google_verification"])

    def test_malformed_owner_and_short_secret_denied(self):
        with self.assertRaises(SnapshotRejected):
            record_verified_snapshot(self.db,self.p(owner="bad/name"),
                server_secret=SECRET,observed_at_ms=NOW)
        with self.assertRaises(SnapshotRejected):
            record_verified_snapshot(self.db,self.p(),
                server_secret=b"short",observed_at_ms=NOW)

    def test_invalid_query_timestamp_denied(self):
        self.record()
        with self.assertRaises(SnapshotRejected):
            self.status(now=True)


class PlayServiceSnapshotIntegration(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        initialize_owners(self.db)
        initialize_snapshot(self.db)

    def tearDown(self):
        self.db.close()

    def verify(self, google, *, owner="alice"):
        return acknowledge_then_verify_subscription(
            db=self.db, purchase_token="service-token-1",
            access_token="synthetic-oauth", authenticated_owner_id=owner,
            product_id=PRODUCT, server_secret=SECRET, now_ms=NOW,
            opener=google,snapshot_recorder=record_verified_snapshot)

    def status(self):
        return diagnostic_snapshot(
            self.db,owner_id="alice",purchase_token="service-token-1",
            product_id=PRODUCT,server_secret=SECRET,now_ms=NOW)

    def test_verified_active_stores_observation_and_binds(self):
        self.assertTrue(self.verify(
            FakeGoogle(purchase(ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))))
        self.assertTrue(self.status()["historically_allowed_at_check"])
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM play_token_owners").fetchone()[0],1)

    def test_hold_after_active_overwrites_on_later_timestamp(self):
        self.verify(FakeGoogle(purchase(
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED")))
        self.assertFalse(acknowledge_then_verify_subscription(
            db=self.db,purchase_token="service-token-1",
            access_token="synthetic",authenticated_owner_id="alice",
            product_id=PRODUCT,server_secret=SECRET,now_ms=NOW+1000,
            opener=FakeGoogle(purchase(state="SUBSCRIPTION_STATE_ON_HOLD",
                ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED")),
            snapshot_recorder=record_verified_snapshot))
        self.assertFalse(self.status()["historically_allowed_at_check"])

    def test_pending_payment_snapshot_denied_without_bind(self):
        self.assertFalse(self.verify(FakeGoogle(purchase(
            state="SUBSCRIPTION_STATE_PENDING"))))
        self.assertFalse(self.status()["historically_allowed_at_check"])
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM play_token_owners").fetchone()[0],0)

    def test_post_ack_snapshots_only_fresh_confirmed_purchase(self):
        g=FakeGoogle(purchase(),200,purchase(
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        self.assertTrue(self.verify(g))
        self.assertEqual([q[0] for q in g.requests],["GET","POST","GET"])
        self.assertTrue(self.status()["historically_allowed_at_check"])

    def test_post_ack_unconfirmed_denied_and_snapshotted(self):
        g=FakeGoogle(purchase(),200,purchase())
        self.assertFalse(self.verify(g))
        self.assertFalse(self.status()["historically_allowed_at_check"])
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM play_token_owners").fetchone()[0],0)

    def test_provider_owner_mismatch_never_snapshotted(self):
        from server.play_subscription_mapper import PlayMappingError
        with self.assertRaises(PlayMappingError):
            self.verify(FakeGoogle(purchase(owner="bob")))
        self.assertIsNone(self.status())

    def test_database_failure_never_grants(self):
        self.db.execute("DROP TABLE play_verified_snapshots")
        with self.assertRaises(sqlite3.OperationalError):
            self.verify(FakeGoogle(purchase(
                ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED")))

    def test_no_recorder_does_not_migrate_automatically(self):
        self.db.execute("DROP TABLE play_verified_snapshots")
        result=acknowledge_then_verify_subscription(
            db=self.db,purchase_token="service-token-2",
            access_token="synthetic",authenticated_owner_id="alice",
            product_id=PRODUCT,server_secret=SECRET,now_ms=NOW,
            opener=FakeGoogle(purchase(
                ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED")))
        self.assertTrue(result)
        self.assertIsNone(self.db.execute(
            "SELECT name FROM sqlite_master WHERE name='play_verified_snapshots'"
        ).fetchone())


class GatewaySnapshotIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.dbfile=self.tmp.name+"/secure.sqlite3"
        with sqlite3.connect(self.dbfile) as db:
            initialize_owners(db)
            initialize_snapshot(db)

    def tearDown(self):
        self.tmp.cleanup()

    def boundary(self, opener):
        return PlayGatewayBoundary(
            server_secret=SECRET, allowed_products={PRODUCT},
            oauth_supplier=lambda: "synthetic-oauth",
            db_factory=lambda: sqlite3.connect(self.dbfile),
            opener=opener, clock_ms=lambda: NOW,
            snapshot_recorder=record_verified_snapshot)

    def test_signed_boundary_requires_fresh_play_get_on_every_check(self):
        first=self.boundary(FakeGoogle(purchase(
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED")))
        self.assertTrue(first.verify(authenticated_owner_id="alice",
                         product_id=PRODUCT,purchase_token="boundary-token"))
        with sqlite3.connect(self.dbfile) as db:
            self.assertTrue(diagnostic_snapshot(db,owner_id="alice",
                purchase_token="boundary-token",product_id=PRODUCT,
                server_secret=SECRET,now_ms=NOW)["requires_live_google_verification"])
        second=self.boundary(FakeGoogle(
            urllib.error.URLError("fake-outage")))
        with self.assertRaises(PlayBoundaryError):
            second.verify(authenticated_owner_id="alice",product_id=PRODUCT,
                          purchase_token="boundary-token")

    def test_boundary_snapshot_write_failure_returns_error(self):
        with sqlite3.connect(self.dbfile) as db:
            db.execute("DROP TABLE play_verified_snapshots")
        obj=self.boundary(FakeGoogle(purchase(
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED")))
        with self.assertRaises(PlayBoundaryError):
            obj.verify(authenticated_owner_id="alice",product_id=PRODUCT,
                       purchase_token="boundary-token")


if __name__=="__main__":
    unittest.main()
