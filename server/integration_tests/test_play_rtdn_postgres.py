"""Real isolated PostgreSQL tests; Google OAuth/provider responses are synthetic.

Run explicitly with OMEGA_ORBA_TEST_PG_DSN against a disposable local orba_test
database. Missing configuration is an error, not a skipped integration test.
These are new tests and do not stand in for an unavailable V41 test package.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from functools import partial
import hashlib
import os
import threading
import time
import unittest
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from server.play_entitlement_gate import PACKAGE, VerifiedPlayPurchase, token_digest
from server.play_rtdn import PlayRtdnProcessor, RtdnDenied, RtdnRetry
from server.play_rtdn_postgres import (
    PostgresRtdnStore, initialize_postgres_rtdn, record_postgres_snapshot,
)
from server.play_rtdn_store import RtdnStoreConflict, RtdnStoreUnavailable
from server.play_verified_snapshot import SnapshotRejected
from server.tests.test_play_acknowledgement_service import FakeGoogle, purchase, SECRET
from server.tests.test_play_rtdn import (
    NOW, AUDIENCE, EMAIL, SUB, PRODUCT, JWT, claims, event, wrapped,
)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class PostgresRtdnTests(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ.get("OMEGA_ORBA_TEST_PG_DSN")
        if not self.dsn:
            raise RuntimeError("OMEGA_ORBA_TEST_PG_DSN must name isolated local orba_test; skips forbidden")
        settings = conninfo_to_dict(self.dsn)
        if (settings.get("host") != "127.0.0.1" or
                settings.get("hostaddr") not in (None, "127.0.0.1") or
                settings.get("dbname") != "orba_test" or
                settings.get("service") is not None):
            raise RuntimeError("only disposable loopback orba_test database is permitted")
        self.schema = "orba_rtdn_" + uuid.uuid4().hex
        with self.connect() as connection:
            if connection.execute("SELECT current_database()").fetchone()[0] != "orba_test":
                raise RuntimeError("authenticated database identity is not orba_test")
            initialize_postgres_rtdn(connection, schema=self.schema)
        self.addCleanup(self.drop_schema)
        self.google = FakeGoogle(purchase(owner="alice",
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        self.clock = NOW
        self.processor = self.make_processor()

    def connect(self):
        return psycopg.connect(self.dsn, autocommit=True, connect_timeout=3)

    def drop_schema(self):
        with self.connect() as connection:
            connection.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                sql.Identifier(self.schema)))

    def make_processor(self, *, factory=None, opener=None, schema=None, recorder=None):
        selected_schema = schema or self.schema
        return PlayRtdnProcessor(
            audience=AUDIENCE, service_account_email=EMAIL, subscription=SUB,
            allowed_products={PRODUCT}, server_secret=SECRET,
            store=PostgresRtdnStore(factory or self.connect, schema=selected_schema),
            oauth_supplier=lambda: "offline-only-google-oauth",
            verifier=lambda *_: claims(),
            provider_opener=opener or (lambda request, timeout: self.google(request, timeout)),
            clock=lambda: self.clock,
            snapshot_recorder=recorder or partial(record_postgres_snapshot, schema=selected_schema),
        )

    def push(self, *, processor=None, message="message-1", notice=None, authorization=None):
        return (processor or self.processor).process(
            authorization="Bearer " + JWT if authorization is None else authorization,
            raw=wrapped(msgid=message, data=notice))

    def bind(self, owner="alice"):
        # Test fixture only. RTDN never binds an unclaimed token itself.
        with self.connect() as connection:
            connection.execute(sql.SQL("INSERT INTO {} (token_sha256,owner_id) VALUES(%s,%s)").format(
                sql.Identifier(self.schema, "play_token_owners")),
                (token_digest("token-one"), owner))

    def rows(self, table):
        with self.connect() as connection:
            return connection.execute(sql.SQL("SELECT * FROM {}").format(
                sql.Identifier(self.schema, table))).fetchall()

    def counts(self):
        return tuple(len(self.rows(table)) for table in (
            "play_rtdn_audit", "play_verified_snapshots", "play_token_owners"))

    def provider_purchase(self, *, owner="alice", state="SUBSCRIPTION_STATE_ACTIVE"):
        return VerifiedPlayPurchase(package_name=PACKAGE, product_id=PRODUCT,
            purchase_token_sha256=token_digest("token-one"), owner_id=owner,
            subscription_state=state, expires_at_ms=NOW * 1000 + 100000,
            acknowledged=True, verified_by_google_api=True)

    def snapshot(self, purchase_value=None, *, at=None, connection=None):
        return record_postgres_snapshot(connection, purchase_value or self.provider_purchase(),
            server_secret=SECRET, observed_at_ms=NOW * 1000 if at is None else at,
            schema=self.schema)

    def test_bound_delivery_commits_snapshot_and_audit(self):
        self.bind()
        self.assertTrue(self.push())
        self.assertEqual(self.counts(), (1, 1, 1))
        self.assertEqual(self.rows("play_verified_snapshots")[0][3], "SUBSCRIPTION_STATE_ACTIVE")
        self.assertEqual(len(self.google.requests), 1)

    def test_two_workers_share_message_lock_and_fetch_google_once(self):
        self.bind()
        provider_entered, release_provider, second_started = (threading.Event() for _ in range(3))
        pids, provider_calls, pids_lock = [], [], threading.Lock()
        def factory():
            connection = self.connect()
            with pids_lock:
                pids.append(connection.info.backend_pid)
            return connection
        def provider(request, timeout):
            with pids_lock:
                provider_calls.append(True)
            provider_entered.set()
            if not release_provider.wait(5):
                raise RuntimeError("test provider release timed out")
            return self.google(request, timeout)
        def second():
            second_started.set()
            return self.push(processor=self.make_processor(factory=factory, opener=provider))
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.push, processor=self.make_processor(factory=factory, opener=provider))
            try:
                self.assertTrue(provider_entered.wait(3))
                later = pool.submit(second)
                self.assertTrue(second_started.wait(3))
                # Prove overlap at PostgreSQL, not merely that both Python
                # functions started. The second backend must be blocked on
                # the first worker's transaction advisory lock before release.
                waiting = False
                deadline = time.monotonic() + 3
                with self.connect() as observer:
                    while time.monotonic() < deadline:
                        with pids_lock:
                            second_pid = pids[1] if len(pids) > 1 else None
                        if second_pid is not None:
                            row = observer.execute("SELECT wait_event_type,wait_event "
                                "FROM pg_catalog.pg_stat_activity WHERE pid=%s",
                                (second_pid,)).fetchone()
                            if row == ("Lock", "advisory"):
                                waiting = True
                                break
                        threading.Event().wait(0.01)
                self.assertTrue(waiting, "second backend did not wait on first message lock")
                self.assertEqual(len(provider_calls), 1)
            finally:
                release_provider.set()
            self.assertTrue(first.result(timeout=5))
            self.assertFalse(later.result(timeout=5))
        self.assertEqual(len(pids), 2)
        self.assertEqual(len(set(pids)), 2)
        self.assertEqual(len(self.google.requests), 1)
        self.assertEqual(len(provider_calls), 1)
        self.assertEqual(self.counts(), (1, 1, 1))

    def test_same_message_id_in_different_subscriptions_has_separate_scope(self):
        first_notice = event(is_test=True)
        self.assertTrue(self.push(notice=first_notice))
        other_subscription = "projects/orba-test/subscriptions/second-rtdn"
        other_processor = self.make_processor()
        other_processor.subscription = other_subscription
        self.assertTrue(other_processor.process(authorization="Bearer " + JWT,
            raw=wrapped(msgid="message-1", data=first_notice, subscription=other_subscription)))
        self.assertEqual(self.counts(), (2, 0, 0))
        self.assertEqual(self.google.requests, [])

    def test_postgres_snapshot_order_ignores_skewed_worker_clocks(self):
        self.bind()
        first = self.make_processor()
        first.clock = lambda: NOW + 1000000
        first.verifier = lambda *_: claims(iat=NOW + 999980, exp=NOW + 1000200)
        self.assertTrue(self.push(processor=first))
        first_observation = self.rows("play_verified_snapshots")[0][7]
        # Ensure the next DB-side fetch starts in a later millisecond.
        threading.Event().wait(0.003)
        self.google = FakeGoogle(purchase(owner="alice", state="SUBSCRIPTION_STATE_ON_HOLD",
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        second = self.make_processor()
        second.clock = lambda: NOW - 1000000
        second.verifier = lambda *_: claims(iat=NOW - 1000020, exp=NOW - 999800)
        self.assertTrue(self.push(processor=second, message="message-2"))
        latest = self.rows("play_verified_snapshots")[0]
        self.assertEqual(latest[3], "SUBSCRIPTION_STATE_ON_HOLD")
        self.assertGreater(latest[7], first_observation)
        self.assertNotEqual(latest[7], (NOW - 1000000) * 1000)

    def test_delayed_older_provider_response_cannot_replace_later_hold(self):
        self.bind()
        first_started, release_first = threading.Event(), threading.Event()
        call_lock, calls = threading.Lock(), []
        active = FakeGoogle(purchase(owner="alice", ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        held = FakeGoogle(purchase(owner="alice", state="SUBSCRIPTION_STATE_ON_HOLD",
            ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        def provider(request, timeout):
            with call_lock:
                calls.append(True)
                order = len(calls)
            if order == 1:
                first_started.set()
                if not release_first.wait(5):
                    raise RuntimeError("test release timed out")
                return active(request, timeout)
            return held(request, timeout)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.push, processor=self.make_processor(opener=provider), message="older")
            try:
                self.assertTrue(first_started.wait(3))
                threading.Event().wait(0.003)
                second = pool.submit(self.push, processor=self.make_processor(opener=provider), message="newer")
                self.assertTrue(second.result(timeout=3))
                self.assertEqual(self.rows("play_verified_snapshots")[0][3], "SUBSCRIPTION_STATE_ON_HOLD")
            finally:
                release_first.set()
            self.assertTrue(first.result(timeout=3))
        self.assertEqual(self.counts(), (2, 1, 1))
        self.assertEqual(self.rows("play_verified_snapshots")[0][3], "SUBSCRIPTION_STATE_ON_HOLD")

    def test_fresh_default_transaction_connection_is_supported(self):
        def factory():
            return psycopg.connect(self.dsn, connect_timeout=3)
        self.assertTrue(self.push(processor=self.make_processor(factory=factory)))
        self.assertEqual(self.counts(), (1, 0, 0))

    def test_factory_with_preexisting_transaction_is_rejected(self):
        def factory():
            connection = psycopg.connect(self.dsn, connect_timeout=3)
            connection.execute("SELECT 1")
            return connection
        with self.assertRaises(RtdnRetry):
            self.push(processor=self.make_processor(factory=factory))
        self.assertEqual(self.google.requests, [])
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_payload_conflict_denied_without_second_provider_call(self):
        self.assertTrue(self.push())
        with self.assertRaisesRegex(RtdnDenied, "MESSAGE_ID_CONFLICT"):
            self.push(notice=event(kind=13))
        self.assertEqual(len(self.google.requests), 1)
        self.assertEqual(self.counts(), (1, 0, 0))

    def test_new_processor_replays_persisted_message(self):
        self.bind()
        self.assertTrue(self.push())
        self.assertFalse(self.push(processor=self.make_processor()))
        self.assertEqual(len(self.google.requests), 1)

    def test_recorder_failure_rolls_back_snapshot_and_audit_then_retry_succeeds(self):
        self.bind()
        def fail_after_write(connection, p, **kwargs):
            record_postgres_snapshot(connection, p, schema=self.schema, **kwargs)
            raise RuntimeError("PRIVATE_DB_ERROR")
        with self.assertRaises(RtdnRetry) as error:
            self.push(processor=self.make_processor(recorder=fail_after_write))
        self.assertNotIn("PRIVATE_DB_ERROR", str(error.exception))
        self.assertEqual(self.counts(), (0, 0, 1))
        self.google = FakeGoogle(purchase(owner="alice", ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"))
        self.assertTrue(self.push())
        self.assertEqual(self.counts(), (1, 1, 1))

    def test_audit_failure_rolls_back_preceding_snapshot(self):
        self.bind()
        with self.connect() as connection:
            connection.execute(sql.SQL("ALTER TABLE {} ADD CONSTRAINT reject_test CHECK(false) NOT VALID").format(
                sql.Identifier(self.schema, "play_rtdn_audit")))
        with self.assertRaises(RtdnRetry):
            self.push()
        self.assertEqual(self.counts(), (0, 0, 1))

    def test_connection_loss_releases_lock_and_rolls_back_snapshot(self):
        store = PostgresRtdnStore(self.connect, schema=self.schema)
        with self.assertRaises(RtdnStoreUnavailable):
            with store.delivery(digest("message-1"), digest("payload-1")) as delivery:
                self.snapshot(connection=delivery.connection)
                delivery.connection.close()
        self.assertEqual(self.counts(), (0, 0, 0))
        # A new independent backend can immediately claim the same message.
        with store.delivery(digest("message-1"), digest("payload-1")) as delivery:
            self.assertFalse(delivery.duplicate)
            delivery.finish(token_digest=None, outcome="TEST", recorded_at_ms=NOW * 1000)
        self.assertEqual(self.counts(), (1, 0, 0))

    def test_exception_releases_message_lock_for_redelivery(self):
        store = PostgresRtdnStore(self.connect, schema=self.schema)
        with self.assertRaisesRegex(RuntimeError, "synthetic abort"):
            with store.delivery(digest("aborted"), digest("payload")):
                raise RuntimeError("synthetic abort")
        with store.delivery(digest("aborted"), digest("payload")) as delivery:
            delivery.finish(token_digest=None, outcome="TEST", recorded_at_ms=NOW * 1000)
        self.assertEqual(self.counts(), (1, 0, 0))

    def test_missing_finish_cannot_commit_partial_snapshot(self):
        with self.assertRaisesRegex(RtdnStoreUnavailable, "NOT_FINISHED"):
            with PostgresRtdnStore(self.connect, schema=self.schema).delivery(
                    digest("message"), digest("payload")) as delivery:
                self.snapshot(connection=delivery.connection)
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_snapshot_requires_active_transaction(self):
        with self.connect() as connection, self.assertRaisesRegex(RtdnStoreUnavailable, "REQUIRES_TRANSACTION"):
            self.snapshot(connection=connection)
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_newer_hold_snapshot_cannot_be_resurrected_by_older_active(self):
        with self.connect() as connection:
            with connection.transaction():
                self.assertTrue(self.snapshot(self.provider_purchase(state="SUBSCRIPTION_STATE_ON_HOLD"),
                    at=NOW * 1000 + 1000, connection=connection))
            with connection.transaction():
                self.assertFalse(self.snapshot(at=NOW * 1000, connection=connection))
        row = self.rows("play_verified_snapshots")[0]
        self.assertEqual(row[3], "SUBSCRIPTION_STATE_ON_HOLD")
        self.assertEqual(row[6], 0)

    def test_snapshot_clock_tie_conflict_rolls_back(self):
        with self.connect() as connection:
            with connection.transaction():
                self.assertTrue(self.snapshot(connection=connection))
            with connection.transaction():
                self.assertFalse(self.snapshot(connection=connection))
            with self.assertRaisesRegex(SnapshotRejected, "CLOCK_TIE_CONFLICT"):
                with connection.transaction():
                    self.snapshot(self.provider_purchase(state="SUBSCRIPTION_STATE_ON_HOLD"), connection=connection)
        self.assertEqual(self.rows("play_verified_snapshots")[0][3], "SUBSCRIPTION_STATE_ACTIVE")

    def test_snapshot_cross_owner_replacement_denied(self):
        with self.connect() as connection:
            with connection.transaction():
                self.snapshot(connection=connection)
            with self.assertRaisesRegex(SnapshotRejected, "OWNER_CONFLICT"):
                with connection.transaction():
                    self.snapshot(self.provider_purchase(owner="bob"), at=NOW * 1000 + 1,
                                  connection=connection)
        self.assertEqual(len(self.rows("play_verified_snapshots")), 1)

    def test_unverified_snapshot_rejected_before_write(self):
        with self.connect() as connection, self.assertRaises(SnapshotRejected):
            with connection.transaction():
                self.snapshot(replace(self.provider_purchase(), verified_by_google_api=False), connection=connection)
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_unbound_token_never_claimed_or_snapshotted(self):
        self.assertTrue(self.push())
        self.assertEqual(self.counts(), (1, 0, 0))
        self.assertEqual(self.rows("play_rtdn_audit")[0][3], "RECHECKED_UNBOUND")

    def test_test_notification_never_calls_google(self):
        self.assertTrue(self.push(notice=event(is_test=True)))
        self.assertEqual(self.counts(), (1, 0, 0))
        self.assertEqual(self.google.requests, [])

    def test_authentication_denied_before_postgres_factory(self):
        calls = []
        def forbidden_factory():
            calls.append(True)
            raise AssertionError("database must not be reached")
        with self.assertRaises(RtdnDenied):
            self.push(processor=self.make_processor(factory=forbidden_factory), authorization="")
        self.assertEqual(calls, [])

    def test_audit_and_snapshot_only_persist_purchase_and_owner_digests(self):
        self.bind()
        self.assertTrue(self.push())
        data = repr(self.rows("play_rtdn_audit") + self.rows("play_verified_snapshots"))
        for secret in ("token-one", "alice", "message-1", SECRET.decode(), "offline-only-google-oauth"):
            self.assertNotIn(secret, data)
        self.assertIn(token_digest("token-one"), data)

    def test_missing_schema_retries_without_automatic_migration(self):
        missing = self.schema + "x"
        with self.assertRaises(RtdnRetry):
            self.push(processor=self.make_processor(schema=missing))
        with self.connect() as connection:
            found = connection.execute("SELECT 1 FROM pg_namespace WHERE nspname=%s", (missing,)).fetchone()
        self.assertIsNone(found)

    def test_schema_scope_ignores_changed_search_path(self):
        self.bind()
        def factory():
            connection = self.connect()
            connection.execute("SET search_path TO pg_catalog")
            return connection
        self.assertTrue(self.push(processor=self.make_processor(factory=factory)))
        self.assertEqual(self.counts(), (1, 1, 1))

    def test_factory_error_redacts_connection_details(self):
        def factory():
            raise psycopg.OperationalError("PRIVATE_DSN_PASSWORD")
        with self.assertRaises(RtdnRetry) as error:
            self.push(processor=self.make_processor(factory=factory))
        self.assertNotIn("PRIVATE_DSN_PASSWORD", str(error.exception))

    def test_repeatable_read_factory_still_sees_prior_delivery(self):
        def factory():
            connection = self.connect()
            connection.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
            return connection
        self.assertTrue(self.push(processor=self.make_processor(factory=factory)))
        self.assertFalse(self.push(processor=self.make_processor(factory=factory)))
        self.assertEqual(len(self.google.requests), 1)

    def test_incomplete_or_invalid_audit_cannot_be_committed(self):
        with self.assertRaises(ValueError):
            with PostgresRtdnStore(self.connect, schema=self.schema).delivery(
                    digest("message"), digest("payload")) as delivery:
                delivery.finish(token_digest=None, outcome="RECHECKED_BOUND", recorded_at_ms=NOW * 1000)
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_direct_store_conflict_preserves_committed_record(self):
        store = PostgresRtdnStore(self.connect, schema=self.schema)
        with store.delivery(digest("message"), digest("payload")) as delivery:
            delivery.finish(token_digest=None, outcome="TEST", recorded_at_ms=NOW * 1000)
        with self.assertRaises(RtdnStoreConflict):
            with store.delivery(digest("message"), digest("different")):
                self.fail("conflicting delivery must not be yielded")
        self.assertEqual(self.counts(), (1, 0, 0))


if __name__ == "__main__":
    unittest.main()
