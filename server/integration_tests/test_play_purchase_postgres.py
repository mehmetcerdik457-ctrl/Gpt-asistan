"""Real PostgreSQL purchase registration and RTDN use one owner ledger.

OAuth, Google provider responses and license purchases remain synthetic.
Run explicitly against disposable local orba_test via OMEGA_ORBA_TEST_PG_DSN.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from psycopg import sql

from server.integration_tests import test_play_rtdn_postgres as postgres_fixture
from server.play_entitlement_gate import token_digest
from server.play_gateway_boundary import PlayGatewayBoundary, PlayBoundaryError
from server.play_owner_binding import OwnershipConflict
from server.play_purchase_postgres import PostgresPlayStore
from server.play_rtdn import ENDPOINT, RtdnRetry
from server.play_rtdn_postgres import record_postgres_snapshot
from server.play_rtdn_store import RtdnStoreUnavailable
from server.tests import test_gateway as gateway_fixture
from server.tests.test_play_acknowledgement_service import FakeGoogle, purchase, SECRET
from server.tests.test_play_rtdn import JWT, NOW, PRODUCT, wrapped


class PostgresPurchaseTests(unittest.TestCase):
    def setUp(self):
        # Compose fixtures through module aliases, avoiding duplicated test
        # discovery from imported/inherited unrelated TestCase classes.
        self.pg = postgres_fixture.PostgresRtdnTests(
            methodName="test_bound_delivery_commits_snapshot_and_audit")
        self.addCleanup(self.pg.doCleanups)
        self.pg.setUp()
        self.store = PostgresPlayStore(self.pg.connect, schema=self.pg.schema)
        self.boundary = self.make_boundary()
        self.pg.processor.store = self.store

    def make_boundary(self, *, store=None, opener=None):
        return PlayGatewayBoundary(server_secret=SECRET, allowed_products={PRODUCT},
            oauth_supplier=lambda: "synthetic-only-publisher-oauth", store=store or self.store,
            opener=opener or (lambda request, timeout: self.pg.google(request, timeout)),
            clock_ms=lambda: NOW * 1000)

    def verify(self, *, owner="alice", boundary=None):
        return (boundary or self.boundary).verify(authenticated_owner_id=owner,
            product_id=PRODUCT, purchase_token="token-one")

    def test_verified_purchase_registers_owner_without_manual_bootstrap_then_rtdn_reconciles(self):
        self.assertTrue(self.verify())
        self.assertEqual(self.pg.counts(), (0, 1, 1))
        self.pg.google = FakeGoogle(purchase(owner="alice", state="SUBSCRIPTION_STATE_ON_HOLD",
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        self.assertTrue(self.pg.push())
        self.assertEqual(self.pg.counts(), (1, 1, 1))
        self.assertEqual(self.pg.rows("play_rtdn_audit")[0][3], "RECHECKED_BOUND")
        self.assertEqual(self.pg.rows("play_verified_snapshots")[0][3], "SUBSCRIPTION_STATE_ON_HOLD")

    def test_pending_ack_requires_get_post_get_before_binding(self):
        self.pg.google = FakeGoogle(purchase(owner="alice"), 200,
            purchase(owner="alice", ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        self.assertTrue(self.verify())
        self.assertEqual([method for method, _ in self.pg.google.requests], ["GET", "POST", "GET"])
        self.assertEqual(self.pg.counts(), (0, 1, 1))

    def test_ack_success_without_provider_confirmation_cannot_bind_or_grant(self):
        self.pg.google = FakeGoogle(purchase(owner="alice"), 200, purchase(owner="alice"))
        self.assertFalse(self.verify())
        self.assertEqual(self.pg.counts(), (0, 1, 0))
        self.assertEqual(self.pg.rows("play_verified_snapshots")[0][6], 0)

    def test_other_owner_rejected_from_ledger_before_google_or_ack(self):
        self.assertTrue(self.verify())
        self.pg.google = FakeGoogle(purchase(owner="bob"))
        with self.assertRaises(PlayBoundaryError):
            self.verify(owner="bob")
        self.assertEqual(self.pg.google.requests, [])
        self.assertEqual(self.pg.rows("play_token_owners")[0][1], "alice")

    def test_provider_owner_mismatch_does_not_register_or_snapshot(self):
        self.pg.google = FakeGoogle(purchase(owner="bob"))
        with self.assertRaises(PlayBoundaryError):
            self.verify()
        self.assertEqual([method for method, _ in self.pg.google.requests], ["GET"])
        self.assertEqual(self.pg.counts(), (0, 0, 0))

    def test_pending_purchase_does_not_create_owner_claim(self):
        self.pg.google = FakeGoogle(purchase(owner="alice", state="SUBSCRIPTION_STATE_PENDING"))
        self.assertFalse(self.verify())
        self.assertEqual(self.pg.counts(), (0, 1, 0))
        self.assertEqual(self.pg.rows("play_verified_snapshots")[0][6], 0)

    def test_purchase_expiring_during_provider_get_is_denied_without_owner_claim(self):
        requests, expiry_times = [], []
        def delayed_provider(request, timeout):
            requests.append(request.get_method())
            with self.pg.connect() as observer:
                expiry_ms = observer.execute("SELECT pg_catalog.floor(EXTRACT(EPOCH FROM "
                    "pg_catalog.clock_timestamp()) * 1000)::bigint").fetchone()[0] + 50
            expiry_times.append(expiry_ms)
            response = purchase(owner="alice", ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED",
                expiry=datetime.fromtimestamp(expiry_ms / 1000, timezone.utc).isoformat(
                    timespec="milliseconds").replace("+00:00", "Z"))
            threading.Event().wait(0.1)
            return FakeGoogle(response)(request, timeout)
        self.assertFalse(self.verify(boundary=self.make_boundary(opener=delayed_provider)))
        self.assertEqual(requests, ["GET"])
        self.assertEqual(self.pg.counts(), (0, 1, 0))
        self.assertLess(self.pg.rows("play_verified_snapshots")[0][7], expiry_times[0])

    def test_positive_snapshot_is_not_authority_when_provider_now_denies(self):
        self.assertTrue(self.verify())
        self.pg.google = FakeGoogle(purchase(owner="alice", state="SUBSCRIPTION_STATE_EXPIRED",
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        self.assertFalse(self.verify())
        self.assertEqual([method for method, _ in self.pg.google.requests], ["GET"])
        self.assertEqual(self.pg.rows("play_verified_snapshots")[0][6], 0)
        self.assertEqual(len(self.pg.rows("play_token_owners")), 1)

    def test_snapshot_write_failure_rolls_back_new_owner_binding(self):
        def write_then_fail(connection, verified, **kwargs):
            record_postgres_snapshot(connection, verified, **kwargs)
            raise RuntimeError("PRIVATE_STORE_FAILURE")
        with patch("server.play_purchase_postgres.record_postgres_snapshot", side_effect=write_then_fail):
            with self.assertRaises(PlayBoundaryError) as error:
                self.verify()
        self.assertNotIn("PRIVATE_STORE_FAILURE", str(error.exception))
        self.assertEqual(self.pg.counts(), (0, 0, 0))

    def test_expiry_during_snapshot_persistence_rolls_back_owner_and_denies(self):
        writes = []
        def short_lived_provider(request, timeout):
            with self.pg.connect() as observer:
                expiry_ms = observer.execute("SELECT pg_catalog.floor(EXTRACT(EPOCH FROM "
                    "pg_catalog.clock_timestamp()) * 1000)::bigint").fetchone()[0] + 2000
            response = purchase(owner="alice", ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED",
                expiry=datetime.fromtimestamp(expiry_ms / 1000, timezone.utc).isoformat(
                    timespec="milliseconds").replace("+00:00", "Z"))
            return FakeGoogle(response)(request, timeout)
        def delayed_snapshot(connection, verified, **kwargs):
            result = record_postgres_snapshot(connection, verified, **kwargs)
            # Observe that both writes really happened before delaying the
            # persistence path past expiry; the separate backend later sees
            # neither write because the final access check must roll back.
            writes.append(connection.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(
                sql.Identifier(self.pg.schema, "play_token_owners"))).fetchone()[0])
            now_ms = connection.execute("SELECT pg_catalog.floor(EXTRACT(EPOCH FROM "
                "pg_catalog.clock_timestamp()) * 1000)::bigint").fetchone()[0]
            threading.Event().wait(max(0, verified.expires_at_ms - now_ms) / 1000 + 0.05)
            return result
        with patch("server.play_purchase_postgres.record_postgres_snapshot", side_effect=delayed_snapshot):
            with self.assertRaises(PlayBoundaryError):
                self.verify(boundary=self.make_boundary(opener=short_lived_provider))
        self.assertEqual(writes, [1])
        self.assertEqual(self.pg.counts(), (0, 0, 0))

    def test_rtdn_audit_failure_preserves_previously_registered_owner_and_snapshot(self):
        self.assertTrue(self.verify())
        self.pg.google = FakeGoogle(purchase(owner="alice", state="SUBSCRIPTION_STATE_ON_HOLD",
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        with self.pg.connect() as connection:
            connection.execute(sql.SQL("ALTER TABLE {} ADD CONSTRAINT deny_audit CHECK(false) NOT VALID").format(
                sql.Identifier(self.pg.schema, "play_rtdn_audit")))
        with self.assertRaises(RtdnRetry):
            self.pg.push()
        self.assertEqual(self.pg.counts(), (0, 1, 1))
        self.assertEqual(self.pg.rows("play_verified_snapshots")[0][3], "SUBSCRIPTION_STATE_ACTIVE")

    def test_two_workers_ack_once_and_both_require_current_provider_checks(self):
        entered, release = threading.Event(), threading.Event()
        provider_lock, calls, pids = threading.Lock(), [], []
        acknowledged = [False]
        def factory():
            connection = self.pg.connect()
            with provider_lock:
                pids.append(connection.info.backend_pid)
            return connection
        def provider(request, timeout):
            method = request.get_method()
            with provider_lock:
                calls.append(method)
                first_call = len(calls) == 1
                if method == "POST":
                    acknowledged[0] = True
                    response = 200
                else:
                    response = purchase(owner="alice", ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"
                        if acknowledged[0] else "ACKNOWLEDGEMENT_STATE_PENDING")
            if first_call:
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("synthetic provider release timed out")
            return FakeGoogle(response)(request, timeout)
        boundary = self.make_boundary(store=PostgresPlayStore(factory, schema=self.pg.schema), opener=provider)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.verify, boundary=boundary)
            try:
                self.assertTrue(entered.wait(3))
                second = pool.submit(self.verify, boundary=boundary)
                waiting = False
                deadline = time.monotonic() + 3
                with self.pg.connect() as observer:
                    while time.monotonic() < deadline:
                        with provider_lock:
                            second_pid = pids[1] if len(pids) > 1 else None
                        if second_pid is not None:
                            row = observer.execute("SELECT wait_event_type,wait_event "
                                "FROM pg_catalog.pg_stat_activity WHERE pid=%s", (second_pid,)).fetchone()
                            if row == ("Lock", "advisory"):
                                waiting = True
                                break
                        threading.Event().wait(0.01)
                self.assertTrue(waiting, "second purchase worker must wait on token verification lock")
                self.assertEqual(calls, ["GET"])
            finally:
                release.set()
            self.assertTrue(first.result(timeout=5))
            self.assertTrue(second.result(timeout=5))
        self.assertEqual(calls, ["GET", "POST", "GET", "GET"])
        self.assertEqual(len(set(pids)), 2)
        self.assertEqual(self.pg.counts(), (0, 1, 1))

    def test_scope_cannot_bind_another_token_or_owner(self):
        with self.store.verification(token_sha256=token_digest("token-one"), authenticated_owner_id="alice") as tx:
            for token, owner in (("another-token", "alice"), ("token-one", "bob")):
                with self.assertRaises(OwnershipConflict):
                    tx.bind_verified_owner(tx.connection, purchase_token=token,
                        authenticated_owner_id=owner, now_ms=NOW * 1000)
        self.assertEqual(self.pg.counts(), (0, 0, 0))

    def test_callbacks_cannot_write_after_transaction_closed(self):
        with self.store.verification(token_sha256=token_digest("token-one"), authenticated_owner_id="alice") as tx:
            pass
        with self.assertRaises(RtdnStoreUnavailable):
            tx.bind_verified_owner(tx.connection, purchase_token="token-one",
                authenticated_owner_id="alice", now_ms=NOW * 1000)
        self.assertEqual(self.pg.counts(), (0, 0, 0))

    def test_new_store_instance_observes_existing_owner_without_copy(self):
        self.assertTrue(self.verify())
        reopened = PostgresPlayStore(self.pg.connect, schema=self.pg.schema)
        self.pg.google = FakeGoogle(purchase(owner="alice", ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        self.assertTrue(self.verify(boundary=self.make_boundary(store=reopened)))
        self.assertEqual(self.pg.counts(), (0, 1, 1))

    def test_purchase_snapshot_and_ledger_store_no_plaintext_token_or_oauth(self):
        self.assertTrue(self.verify())
        persisted = repr(self.pg.rows("play_token_owners") + self.pg.rows("play_verified_snapshots"))
        self.assertNotIn("token-one", persisted)
        self.assertNotIn("synthetic-only-publisher-oauth", persisted)
        self.assertNotIn(SECRET.decode(), persisted)
        self.assertIn(token_digest("token-one"), persisted)


class PostgresPurchaseHttpTests(unittest.TestCase):
    def setUp(self):
        self.pg = postgres_fixture.PostgresRtdnTests(
            methodName="test_bound_delivery_commits_snapshot_and_audit")
        self.addCleanup(self.pg.doCleanups)
        self.pg.setUp()
        self.enterContext(patch.dict(os.environ, {
            "ORBA_PLAY_BOUNDARY_ENABLED": "YES", "ORBA_PLAY_RTDN_ENABLED": "YES"}))
        self.http = gateway_fixture.GatewayHttpTests(methodName="test_no_provider_calls_without_auth")
        self.http.setUp()
        self.addCleanup(self.http.tearDown)
        self.store = PostgresPlayStore(self.pg.connect, schema=self.pg.schema)
        self.boundary = PlayGatewayBoundary(server_secret=SECRET, allowed_products={PRODUCT},
            oauth_supplier=lambda: "offline-only-oauth", store=self.store,
            opener=lambda request, timeout: self.pg.google(request, timeout),
            clock_ms=lambda: NOW * 1000)
        self.http.gateway.play_boundary = self.boundary
        self.pg.processor.store = self.store
        self.http.gateway.rtdn_processor = self.pg.processor

    def push(self):
        request = urllib.request.Request(self.http.url + ENDPOINT, data=wrapped(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + JWT}, method="POST")
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def test_signed_http_purchase_registers_then_authenticated_rtdn_uses_same_owner(self):
        self.pg.google = FakeGoogle(purchase(owner="owner-test", ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        status, body = self.http.post("play/verify", {"productId": PRODUCT, "purchaseToken": "token-one"})
        self.assertEqual((status, body["entitled"]), (200, True))
        self.assertEqual(self.pg.counts(), (0, 1, 1))
        self.pg.google = FakeGoogle(purchase(owner="owner-test", state="SUBSCRIPTION_STATE_ON_HOLD",
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        status, body = self.push()
        self.assertEqual((status, body["rtdn"], body["entitlement_changed"]), (200, "AUDITED", False))
        self.assertEqual(self.pg.rows("play_rtdn_audit")[0][3], "RECHECKED_BOUND")
        self.assertEqual(self.pg.rows("play_verified_snapshots")[0][3], "SUBSCRIPTION_STATE_ON_HOLD")
        self.assertEqual(self.pg.counts(), (1, 1, 1))
        self.assertEqual(self.http.provider.calls, [])

    def test_unsigned_purchase_never_claims_pg_owner(self):
        status, body = self.http.post("play/verify", {"productId": PRODUCT, "purchaseToken": "token-one"},
            headers={"Content-Type": "application/json"})
        self.assertEqual((status, body["error"]), (403, "OWNER_AUTH_REQUIRED"))
        self.assertEqual(self.pg.counts(), (0, 0, 0))
        self.assertEqual(self.pg.google.requests, [])

    def test_snapshot_failure_after_verified_http_purchase_returns_503_and_no_owner_claim(self):
        self.pg.google = FakeGoogle(purchase(owner="owner-test", ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        with self.pg.connect() as connection:
            connection.execute(sql.SQL("ALTER TABLE {} ADD CONSTRAINT deny_snapshot CHECK(false) NOT VALID").format(
                sql.Identifier(self.pg.schema, "play_verified_snapshots")))
        status, body = self.http.post("play/verify", {"productId": PRODUCT, "purchaseToken": "token-one"})
        self.assertEqual((status, body["error"]), (503, "PLAY_VERIFICATION_UNAVAILABLE"))
        self.assertEqual(self.pg.counts(), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
