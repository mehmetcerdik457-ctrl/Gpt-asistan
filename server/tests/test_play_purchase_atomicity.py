"""Purchase transaction and expiry regressions with real SQLite, fake Google.

These tests exercise failure points after a verified lookup and owner write,
and advance a trusted server clock while provider calls are in flight. No
network, credentials, inherited TestCase tests or PostgreSQL are required.
"""
from contextlib import closing
from datetime import datetime, timezone
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from server.play_gateway_boundary import PlayBoundaryError, PlayGatewayBoundary
from server.play_owner_binding import (
    OwnershipConflict, bind_or_verify_owner, initialize as initialize_owners,
)
from server.play_verified_snapshot import initialize_snapshot, record_verified_snapshot
from server.play_verification_service import verify_play_entitlement
from server.tests import test_play_acknowledgement_service as provider_fixture


NOW = provider_fixture.NOW
PRODUCT = provider_fixture.PRODUCT
SECRET = provider_fixture.SECRET
TOKEN = "atomic-purchase-token"
ACKED = "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"


def expiry_at(value_ms):
    return datetime.fromtimestamp(value_ms / 1000, timezone.utc).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")


class PurchaseAtomicityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dbpath = tmp.name + "/purchase.sqlite3"
        self.now = NOW
        with closing(self.connect()) as db:
            initialize_owners(db)
            initialize_snapshot(db)

    def connect(self):
        return sqlite3.connect(self.dbpath)

    def boundary(self, google, *, recorder=record_verified_snapshot):
        return PlayGatewayBoundary(
            server_secret=SECRET, allowed_products={PRODUCT},
            oauth_supplier=lambda: "synthetic-offline-oauth",
            db_factory=self.connect, opener=google,
            clock_ms=lambda: self.now, snapshot_recorder=recorder,
        )

    def verify(self, boundary):
        return boundary.verify(authenticated_owner_id="alice", product_id=PRODUCT,
                               purchase_token=TOKEN)

    def rows(self):
        with closing(self.connect()) as db:
            return (
                db.execute("SELECT owner_id,created_at_ms FROM play_token_owners").fetchall(),
                db.execute("SELECT observed_at_ms FROM play_verified_snapshots").fetchall(),
            )

    def acknowledged_google(self):
        return provider_fixture.FakeGoogle(provider_fixture.purchase(ack=ACKED))

    def test_successful_verification_commits_binding_and_snapshot_together(self):
        google = self.acknowledged_google()
        self.assertIs(self.verify(self.boundary(google)), True)
        self.assertEqual(self.rows(), ([("alice", NOW)], [(NOW,)]))
        self.assertEqual([method for method, _ in google.requests], ["GET"])

    def test_recorder_write_then_exception_rolls_back_new_owner_and_snapshot(self):
        observed = []

        def write_then_fail(db, *args, **kwargs):
            record_verified_snapshot(db, *args, **kwargs)
            observed.append((
                db.execute("SELECT COUNT(*) FROM play_token_owners").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM play_verified_snapshots").fetchone()[0],
            ))
            raise RuntimeError("PRIVATE_PURCHASE_RECORDER_FAILURE")

        boundary = self.boundary(self.acknowledged_google(), recorder=write_then_fail)
        with self.assertRaises(PlayBoundaryError) as caught:
            self.verify(boundary)
        self.assertNotIn("PRIVATE_PURCHASE_RECORDER_FAILURE", str(caught.exception))
        self.assertEqual(observed, [(1, 1)])
        self.assertEqual(self.rows(), ([], []))
        # A fresh request may bind again; no failed attempt reserved ownership.
        self.assertIs(self.verify(self.boundary(self.acknowledged_google())), True)
        self.assertEqual(self.rows(), ([("alice", NOW)], [(NOW,)]))

    def test_snapshot_sql_failure_cannot_leave_a_committed_owner(self):
        with closing(self.connect()) as db:
            db.execute("""CREATE TRIGGER reject_purchase_snapshot
                BEFORE INSERT ON play_verified_snapshots BEGIN
                SELECT RAISE(ABORT, 'PRIVATE_SNAPSHOT_FAILURE'); END""")
            db.commit()
        with self.assertRaises(PlayBoundaryError) as caught:
            self.verify(self.boundary(self.acknowledged_google()))
        self.assertNotIn("PRIVATE_SNAPSHOT_FAILURE", str(caught.exception))
        self.assertEqual(self.rows(), ([], []))

    def test_preexisting_conflicting_owner_is_rejected_before_google_or_ack(self):
        with closing(self.connect()) as db:
            bind_or_verify_owner(db, purchase_token=TOKEN,
                                 authenticated_owner_id="bob", now_ms=NOW - 1)
        google = provider_fixture.FakeGoogle(provider_fixture.purchase(), 200,
                                             provider_fixture.purchase(ack=ACKED))
        with self.assertRaises(PlayBoundaryError):
            self.verify(self.boundary(google))
        self.assertEqual(google.requests, [])
        self.assertEqual(self.rows(), ([("bob", NOW - 1)], []))

    def test_owner_binder_exception_after_write_rolls_back_before_snapshot(self):
        original = bind_or_verify_owner

        def bind_then_fail(db, **kwargs):
            original(db, **kwargs)
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM play_token_owners").fetchone()[0], 1)
            raise RuntimeError("PRIVATE_OWNER_CALLBACK_FAILURE")

        with patch("server.play_purchase_store.bind_or_verify_owner", bind_then_fail):
            with self.assertRaises(PlayBoundaryError) as caught:
                self.verify(self.boundary(self.acknowledged_google()))
        self.assertNotIn("PRIVATE_OWNER_CALLBACK_FAILURE", str(caught.exception))
        self.assertEqual(self.rows(), ([], []))

    def test_owner_binder_conflict_preserves_caller_transaction_until_rollback(self):
        with closing(self.connect()) as writer:
            writer.execute("CREATE TABLE caller_work (item TEXT)")
            writer.commit()
            writer.execute("BEGIN IMMEDIATE")
            writer.execute("INSERT INTO caller_work VALUES ('uncommitted work')")
            bind_or_verify_owner(writer, purchase_token=TOKEN,
                                 authenticated_owner_id="alice", now_ms=NOW)
            with self.assertRaises(OwnershipConflict):
                bind_or_verify_owner(writer, purchase_token=TOKEN,
                                     authenticated_owner_id="bob", now_ms=NOW + 1)
            self.assertTrue(writer.in_transaction)
            self.assertEqual(writer.execute("SELECT item FROM caller_work").fetchall(),
                             [("uncommitted work",)])
            self.assertEqual(writer.execute(
                "SELECT owner_id FROM play_token_owners").fetchall(), [("alice",)])
            self.assertEqual(self.rows(), ([], []))
            writer.rollback()
            self.assertEqual(writer.execute("SELECT * FROM caller_work").fetchall(), [])
        self.assertEqual(self.rows(), ([], []))

    def test_pending_ack_purchase_expiring_during_first_get_denies_without_ack(self):
        expires = NOW + 20
        google = provider_fixture.FakeGoogle(
            provider_fixture.purchase(expiry=expiry_at(expires)))

        def delayed_get(request, timeout):
            response = google(request, timeout)
            self.now = expires
            return response

        self.assertIs(self.verify(self.boundary(delayed_get)), False)
        self.assertEqual([method for method, _ in google.requests], ["GET"])
        self.assertEqual(self.rows(), ([], [(NOW,)]))

    def test_acknowledged_purchase_expiring_during_get_denies_without_binding(self):
        expires = NOW + 20
        google = provider_fixture.FakeGoogle(
            provider_fixture.purchase(ack=ACKED, expiry=expiry_at(expires)))

        def delayed_get(request, timeout):
            response = google(request, timeout)
            self.now = expires + 1
            return response

        self.assertIs(self.verify(self.boundary(delayed_get)), False)
        self.assertEqual([method for method, _ in google.requests], ["GET"])
        self.assertEqual(self.rows(), ([], [(NOW,)]))

    def test_expiry_during_post_ack_get_denies_and_uses_that_get_observation(self):
        expires = NOW + 20
        google = provider_fixture.FakeGoogle(
            provider_fixture.purchase(expiry=expiry_at(expires)), 200,
            provider_fixture.purchase(ack=ACKED, expiry=expiry_at(expires)),
        )

        def delayed_provider(request, timeout):
            response = google(request, timeout)
            if len(google.requests) == 2:
                self.now = NOW + 15
            elif len(google.requests) == 3:
                self.now = expires
            return response

        self.assertIs(self.verify(self.boundary(delayed_provider)), False)
        self.assertEqual([method for method, _ in google.requests], ["GET", "POST", "GET"])
        self.assertEqual(self.rows(), ([], [(NOW + 15,)]))

    def test_post_ack_snapshot_orders_by_second_get_start_and_binding_by_decision(self):
        google = provider_fixture.FakeGoogle(provider_fixture.purchase(), 200,
                                             provider_fixture.purchase(ack=ACKED))
        times = iter((NOW + 2, NOW + 5, NOW + 8))

        def timed_provider(request, timeout):
            response = google(request, timeout)
            self.now = next(times)
            return response

        self.assertIs(self.verify(self.boundary(timed_provider)), True)
        self.assertEqual([method for method, _ in google.requests], ["GET", "POST", "GET"])
        self.assertEqual(self.rows(), ([("alice", NOW + 8)], [(NOW + 5,)]))

    def test_expiry_while_snapshot_is_written_rolls_back_before_returning_grant(self):
        expires = NOW + 20
        observed = []
        google = provider_fixture.FakeGoogle(
            provider_fixture.purchase(ack=ACKED, expiry=expiry_at(expires)))

        def write_then_expire(db, *args, **kwargs):
            record_verified_snapshot(db, *args, **kwargs)
            observed.append((
                db.execute("SELECT COUNT(*) FROM play_token_owners").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM play_verified_snapshots").fetchone()[0],
            ))
            self.now = expires

        with self.assertRaises(PlayBoundaryError):
            self.verify(self.boundary(google, recorder=write_then_expire))
        self.assertEqual(observed, [(1, 1)])
        self.assertEqual([method for method, _ in google.requests], ["GET"])
        self.assertEqual(self.rows(), ([], []))

    def test_invalid_or_regressing_response_clock_cannot_bind_or_snapshot(self):
        for bad_clock in (True, float(NOW), NOW - 1):
            with self.subTest(clock=bad_clock):
                self.now = NOW
                google = self.acknowledged_google()

                def bad_response_clock(request, timeout):
                    response = google(request, timeout)
                    self.now = bad_clock
                    return response

                with self.assertRaises(PlayBoundaryError):
                    self.verify(self.boundary(bad_response_clock))
                self.assertEqual([method for method, _ in google.requests], ["GET"])
                self.assertEqual(self.rows(), ([], []))

    def test_regressing_clock_during_ack_refuses_second_get_and_owner_binding(self):
        google = provider_fixture.FakeGoogle(provider_fixture.purchase(), 200)

        def regressing_ack_clock(request, timeout):
            response = google(request, timeout)
            if request.get_method() == "POST":
                self.now = NOW - 1
            return response

        with self.assertRaises(PlayBoundaryError):
            self.verify(self.boundary(regressing_ack_clock))
        self.assertEqual([method for method, _ in google.requests], ["GET", "POST"])
        self.assertEqual(self.rows(), ([], []))

    def test_legacy_verification_rechecks_expiry_after_provider_response(self):
        expires = NOW + 20
        google = provider_fixture.FakeGoogle(
            provider_fixture.purchase(ack=ACKED, expiry=expiry_at(expires)))

        def delayed_get(request, timeout):
            response = google(request, timeout)
            self.now = expires
            return response

        with closing(self.connect()) as db:
            self.assertIs(verify_play_entitlement(
                db=db, purchase_token=TOKEN, access_token="synthetic-offline-oauth",
                authenticated_owner_id="alice", product_id=PRODUCT,
                server_secret=SECRET, now_ms=NOW, opener=delayed_get,
                clock_ms=lambda: self.now,
            ), False)
        self.assertEqual(self.rows(), ([], []))

    def test_commit_delay_cannot_return_a_grant_after_monotonic_expiry_deadline(self):
        google = provider_fixture.FakeGoogle(
            provider_fixture.purchase(ack=ACKED, expiry=expiry_at(NOW + 20)))
        # The observer reads a still-valid purchase before commit; the response
        # deadline has elapsed when the transaction context returns. Ownership
        # remains legitimate and durable, but this response grants no access.
        with patch("server.play_gateway_boundary.time.monotonic", side_effect=(10.0, 10.021)):
            self.assertIs(self.verify(self.boundary(google)), False)
        self.assertEqual(self.rows(), ([("alice", NOW)], [(NOW,)]))

    def test_legacy_verification_denies_expiry_while_owner_binder_waits(self):
        def delayed_binding(db, **kwargs):
            result = bind_or_verify_owner(db, **kwargs)
            self.now = NOW + 20
            return result

        google = provider_fixture.FakeGoogle(
            provider_fixture.purchase(ack=ACKED, expiry=expiry_at(NOW + 20)))
        with closing(self.connect()) as db, self.assertRaisesRegex(ValueError, "EXPIRED"):
            verify_play_entitlement(
                db=db, purchase_token=TOKEN, access_token="synthetic-offline-oauth",
                authenticated_owner_id="alice", product_id=PRODUCT,
                server_secret=SECRET, now_ms=NOW, opener=google,
                clock_ms=lambda: self.now, owner_binder=delayed_binding)


if __name__ == "__main__":
    unittest.main()
