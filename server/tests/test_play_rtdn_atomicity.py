"""SQLite RTDN delivery atomicity with independent connections and fake Google.

The concurrency tests coordinate an in-flight provider lookup and a second
writer attempt without timing sleeps. No live credentials or network calls.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
import sqlite3
import tempfile
import threading
import unittest

from server.play_entitlement_gate import PACKAGE, VerifiedPlayPurchase, token_digest
from server.play_owner_binding import initialize as initialize_owners, bind_or_verify_owner
from server.play_rtdn import PlayRtdnProcessor, RtdnDenied, RtdnRetry, initialize_rtdn
from server.play_verified_snapshot import (
    diagnostic_snapshot, initialize_snapshot, record_verified_snapshot,
)
from server.tests.test_play_acknowledgement_service import FakeGoogle, purchase, SECRET
from server.tests.test_play_rtdn import (
    AUDIENCE, EMAIL, JWT, NOW, PRODUCT, SUB, claims, event, wrapped,
)


class RtdnAtomicityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dbpath = tmp.name + "/atomic-rtdn.sqlite3"
        with closing(self.connect()) as db:
            initialize_owners(db)
            initialize_rtdn(db)
            initialize_snapshot(db)
            bind_or_verify_owner(
                db, purchase_token="token-one", authenticated_owner_id="alice",
                now_ms=NOW * 1000,
            )

    def connect(self):
        return sqlite3.connect(self.dbpath, timeout=5)

    def google(self, state="SUBSCRIPTION_STATE_ACTIVE", count=1):
        return FakeGoogle(*[
            purchase(owner="alice", state=state,
                     ack="ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED")
            for _ in range(count)
        ])

    def processor(self, google, *, db_factory=None, recorder=record_verified_snapshot):
        return PlayRtdnProcessor(
            audience=AUDIENCE, service_account_email=EMAIL, subscription=SUB,
            allowed_products={PRODUCT}, server_secret=SECRET,
            db_factory=db_factory or self.connect,
            oauth_supplier=lambda: "synthetic-offline-oauth",
            verifier=lambda token, audience: claims(), provider_opener=google,
            clock=lambda: NOW, snapshot_recorder=recorder,
        )

    def push(self, processor, raw=None):
        return processor.process(
            authorization="Bearer " + JWT,
            raw=wrapped() if raw is None else raw,
        )

    def snapshot(self, db=None):
        if db is None:
            with closing(self.connect()) as reader:
                return self.snapshot(reader)
        return diagnostic_snapshot(
            db, owner_id="alice", purchase_token="token-one",
            product_id=PRODUCT, server_secret=SECRET, now_ms=NOW * 1000,
        )

    def counts(self):
        with closing(self.connect()) as db:
            return tuple(db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                         for table in ("play_rtdn_audit", "play_verified_snapshots"))

    def verified(self):
        return VerifiedPlayPurchase(
            package_name=PACKAGE, product_id=PRODUCT,
            purchase_token_sha256=token_digest("token-one"), owner_id="alice",
            expires_at_ms=NOW * 1000 + 100000,
            subscription_state="SUBSCRIPTION_STATE_ACTIVE", acknowledged=True,
            verified_by_google_api=True,
        )

    def contending_deliveries(self, second_raw, *, conflict=False):
        provider_entered = threading.Event()
        release_provider = threading.Event()
        second_attempted_writer = threading.Event()
        first_google = self.google()
        second_google = self.google("SUBSCRIPTION_STATE_ON_HOLD")

        def blocked_provider(request, timeout):
            provider_entered.set()
            if not release_provider.wait(5):
                raise TimeoutError("TEST_PROVIDER_RELEASE_TIMEOUT")
            return first_google(request, timeout)

        def second_connection():
            db = self.connect()
            db.set_trace_callback(lambda sql: second_attempted_writer.set()
                                  if sql == "BEGIN IMMEDIATE" else None)
            return db

        first = self.processor(blocked_provider)
        second = self.processor(second_google, db_factory=second_connection)
        self.assertIsNot(first, second)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first_result = pool.submit(self.push, first)
            try:
                self.assertTrue(provider_entered.wait(5), "first lookup did not start")
                second_result = pool.submit(self.push, second, second_raw)
                self.assertTrue(second_attempted_writer.wait(5),
                                "second connection did not attempt its writer lock")
                # Keep the first provider in flight until the independent
                # processor has actually attempted the same database lock.
                release_provider.set()
                self.assertIs(first_result.result(timeout=10), True)
                if conflict:
                    with self.assertRaisesRegex(RtdnDenied, "RTDN_MESSAGE_ID_CONFLICT"):
                        second_result.result(timeout=10)
                else:
                    self.assertIs(second_result.result(timeout=10), False)
            finally:
                release_provider.set()
        self.assertEqual(len(first_google.requests), 1)
        self.assertEqual(second_google.requests, [])
        self.assertEqual(self.counts(), (1, 1))
        self.assertEqual(self.snapshot()["last_provider_state"],
                         "SUBSCRIPTION_STATE_ACTIVE")

    def test_independent_processors_deduplicate_concurrent_delivery_before_google(self):
        self.contending_deliveries(wrapped())

    def test_concurrent_message_id_payload_conflict_cannot_replace_snapshot(self):
        self.contending_deliveries(wrapped(data=event(kind=13)), conflict=True)

    def test_audit_failure_rolls_back_snapshot_and_same_message_can_retry(self):
        writes = []

        def record_and_observe(db, *args, **kwargs):
            result = record_verified_snapshot(db, *args, **kwargs)
            writes.append(self.snapshot(db))
            return result

        google = self.google(count=2)
        processor = self.processor(google, recorder=record_and_observe)
        with closing(self.connect()) as db:
            db.execute("""CREATE TRIGGER fail_rtdn_audit
                BEFORE INSERT ON play_rtdn_audit BEGIN
                SELECT RAISE(ABORT, 'PRIVATE_AUDIT_FAILURE'); END""")
            db.commit()
        with self.assertRaises(RtdnRetry) as caught:
            self.push(processor)
        self.assertNotIn("PRIVATE_AUDIT_FAILURE", str(caught.exception))
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0]["last_provider_state"], "SUBSCRIPTION_STATE_ACTIVE")
        self.assertEqual(self.counts(), (0, 0))
        self.assertIsNone(self.snapshot())
        with closing(self.connect()) as db:
            db.execute("DROP TRIGGER fail_rtdn_audit")
            db.commit()
        self.assertIs(self.push(processor), True)
        self.assertEqual(self.counts(), (1, 1))
        self.assertEqual(len(google.requests), 2)

    def test_snapshot_callback_that_writes_then_raises_rolls_back_and_retries(self):
        writes = []

        def write_then_fail(db, *args, **kwargs):
            record_verified_snapshot(db, *args, **kwargs)
            writes.append(self.snapshot(db))
            raise RuntimeError("PRIVATE_CALLBACK_FAILURE")

        google = self.google(count=2)
        processor = self.processor(google, recorder=write_then_fail)
        with self.assertRaises(RtdnRetry) as caught:
            self.push(processor)
        self.assertNotIn("PRIVATE_CALLBACK_FAILURE", str(caught.exception))
        self.assertEqual(len(writes), 1)
        self.assertIsNotNone(writes[0])
        self.assertEqual(self.counts(), (0, 0))
        self.assertIsNone(self.snapshot())
        processor.snapshot_recorder = record_verified_snapshot
        self.assertIs(self.push(processor), True)
        self.assertEqual(self.counts(), (1, 1))
        self.assertEqual(len(google.requests), 2)

    def test_snapshot_insert_in_outer_transaction_is_invisible_until_commit(self):
        with closing(self.connect()) as writer:
            writer.execute("BEGIN IMMEDIATE")
            self.assertTrue(record_verified_snapshot(
                writer, self.verified(), server_secret=SECRET,
                observed_at_ms=NOW * 1000,
            ))
            self.assertTrue(writer.in_transaction)
            self.assertIsNotNone(self.snapshot(writer))
            self.assertIsNone(self.snapshot())
            writer.commit()
        self.assertEqual(self.snapshot()["last_provider_state"],
                         "SUBSCRIPTION_STATE_ACTIVE")

    def test_snapshot_update_in_outer_transaction_is_undone_by_caller_rollback(self):
        with closing(self.connect()) as writer:
            record_verified_snapshot(
                writer, self.verified(), server_secret=SECRET,
                observed_at_ms=NOW * 1000,
            )
            writer.execute("BEGIN IMMEDIATE")
            self.assertTrue(record_verified_snapshot(
                writer, replace(self.verified(),
                                subscription_state="SUBSCRIPTION_STATE_ON_HOLD"),
                server_secret=SECRET, observed_at_ms=NOW * 1000 + 1000,
            ))
            self.assertTrue(writer.in_transaction)
            self.assertEqual(self.snapshot(writer)["last_provider_state"],
                             "SUBSCRIPTION_STATE_ON_HOLD")
            self.assertEqual(self.snapshot()["last_provider_state"],
                             "SUBSCRIPTION_STATE_ACTIVE")
            writer.rollback()
            self.assertEqual(self.snapshot(writer)["last_provider_state"],
                             "SUBSCRIPTION_STATE_ACTIVE")
        self.assertEqual(self.snapshot()["last_provider_state"],
                         "SUBSCRIPTION_STATE_ACTIVE")

    def test_busy_writer_retries_without_google_then_succeeds_after_release(self):
        google = self.google()
        processor = self.processor(
            google, db_factory=lambda: sqlite3.connect(self.dbpath, timeout=0),
        )
        with closing(self.connect()) as blocker:
            blocker.execute("BEGIN IMMEDIATE")
            with self.assertRaisesRegex(RtdnRetry, "RTDN_STORE_UNAVAILABLE"):
                self.push(processor)
            self.assertEqual(google.requests, [])
            self.assertEqual(self.counts(), (0, 0))
            blocker.rollback()
        self.assertIs(self.push(processor), True)
        self.assertEqual(len(google.requests), 1)
        self.assertEqual(self.counts(), (1, 1))
