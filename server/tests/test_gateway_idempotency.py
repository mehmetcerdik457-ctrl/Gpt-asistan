"""Storage fault injection verifies that chat retries never repeat provider POSTs."""
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from server import gateway as g, idempotency
from server.tests.test_gateway import SyntheticProvider


class ChatIdempotencyFailureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = g.Store(self.tmp.name + "/gateway.sqlite3")
        self.provider = SyntheticProvider()
        self.gateway = g.Gateway(self.store, self.provider)
        self.model = self.gateway.verified_models()["models"][0]["id"]

    def tearDown(self):
        self.gateway.tasks.close()
        self.tmp.cleanup()

    def payload(self, key):
        return {"message": "Merhaba", "model": self.model,
                "include_memory": True, "idempotency_key": key}

    def state(self, key):
        with self.store.connect() as db:
            return db.execute("SELECT state FROM idempotency_ledger WHERE key_sha256=?",
                              (idempotency.key_digest(key),)).fetchone()[0]

    def test_memory_failure_releases_reservation_before_any_provider_post(self):
        for key, failure in (
            ("memory-primary", [sqlite3.OperationalError("synthetic storage failure")]),
            ("memory-fallback", [[], sqlite3.OperationalError("synthetic fallback failure")]),
        ):
            with self.subTest(key=key):
                calls_before = len(self.provider.calls)
                data = self.payload(key)
                with patch.object(self.store, "recall", side_effect=failure):
                    with self.assertRaises(sqlite3.OperationalError):
                        self.gateway.chat(data)
                self.assertEqual(self.state(key), "failed")
                self.assertEqual(len(self.provider.calls), calls_before)
                with patch.object(self.store, "recall", return_value=[]):
                    reply = self.gateway.chat(data)
                    self.assertEqual(self.gateway.chat(data), reply)
                self.assertEqual(self.state(key), "completed")
                self.assertEqual(len(self.provider.calls), calls_before + 1)

    def test_unknown_provider_outcome_cannot_be_replayed_with_same_key(self):
        for key, failure in (
            ("provider-timeout", TimeoutError("synthetic uncertain POST outcome")),
            ("provider-denied", g.Denied("PROVIDER_HTTP_FAILURE", 502)),
        ):
            with self.subTest(key=key):
                data = self.payload(key)
                with patch.object(self.store, "recall", return_value=[]), \
                     patch.object(self.provider, "reply_with_metadata", side_effect=failure) as post:
                    with self.assertRaises(type(failure)):
                        self.gateway.chat(data)
                    self.assertEqual(self.state(key), "processing")
                    # A new explicit probe may re-verify the model after denial,
                    # but cannot authorize replay of the already-attempted chat.
                    self.gateway.verified_models()
                    with self.assertRaises(g.Denied) as denied:
                        self.gateway.chat(data)
                self.assertEqual(denied.exception.code, "IDEMPOTENCY_REQUEST_IN_PROGRESS")
                self.assertEqual(post.call_count, 1)

    def test_save_failure_after_provider_success_keeps_replay_blocked(self):
        data = self.payload("save-after-provider")
        calls_before = len(self.provider.calls)
        with patch.object(self.store, "recall", return_value=[]), \
             patch.object(self.store, "add_chat_idempotent", side_effect=sqlite3.OperationalError("synthetic save failure")):
            with self.assertRaises(sqlite3.OperationalError):
                self.gateway.chat(data)
        self.assertEqual(self.state(data["idempotency_key"]), "processing")
        with self.assertRaises(g.Denied) as denied:
            self.gateway.chat(data)
        self.assertEqual(denied.exception.code, "IDEMPOTENCY_REQUEST_IN_PROGRESS")
        self.assertEqual(len(self.provider.calls), calls_before + 1)


if __name__ == "__main__":
    unittest.main()
