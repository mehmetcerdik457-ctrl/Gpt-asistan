import sqlite3
import unittest
from server import idempotency


class IdempotencyLedgerTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        idempotency.initialize(self.db)

    def tearDown(self):
        self.db.close()

    def test_completed_result_is_replayed(self):
        key = "operation-0001"
        digest = idempotency.request_digest({"b": 2, "a": 1})
        self.assertIsNone(idempotency.reserve(self.db, key, digest))
        self.db.commit()
        self.db.execute("BEGIN IMMEDIATE")
        idempotency.complete(self.db, key, digest, {"text": "saved"})
        self.db.commit()
        self.assertEqual(idempotency.reserve(self.db, key, digest), {"text": "saved"})
        self.db.commit()

    def test_same_key_with_changed_payload_is_rejected(self):
        key = "operation-0002"
        first = idempotency.request_digest({"message": "one"})
        second = idempotency.request_digest({"message": "two"})
        self.assertIsNone(idempotency.reserve(self.db, key, first))
        self.db.commit()
        with self.assertRaises(ValueError):
            idempotency.reserve(self.db, key, second)
        self.db.rollback()

    def test_digest_is_canonical_and_sha256_length(self):
        self.assertEqual(
            idempotency.request_digest({"b": 2, "a": 1}),
            idempotency.request_digest({"a": 1, "b": 2})
        )
        self.assertEqual(64, len(idempotency.request_digest({"ok": True})))


if __name__ == "__main__":
    unittest.main(verbosity=2)
