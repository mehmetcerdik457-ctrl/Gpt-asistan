import sqlite3
import tempfile
import os
import unittest
from server.play_owner_binding import initialize, bind_or_verify_owner, OwnershipConflict
from server.play_entitlement_gate import token_digest


class OwnerBindingTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        initialize(self.db)

    def tearDown(self):
        self.db.close()

    def test_first_binding(self):
        self.assertEqual(bind_or_verify_owner(self.db, purchase_token="token1", authenticated_owner_id="alice", now_ms=1), token_digest("token1"))
    def test_same_owner_retry(self):
        for _ in range(2):
            bind_or_verify_owner(self.db, purchase_token="token1", authenticated_owner_id="alice", now_ms=1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM play_token_owners").fetchone()[0], 1)
    def test_cross_owner_rejected(self):
        bind_or_verify_owner(self.db, purchase_token="token1", authenticated_owner_id="alice", now_ms=1)
        with self.assertRaises(OwnershipConflict):
            bind_or_verify_owner(self.db, purchase_token="token1", authenticated_owner_id="bob", now_ms=2)
        self.assertEqual(self.db.execute("SELECT owner_id FROM play_token_owners").fetchone()[0], "alice")
    def test_distinct_tokens(self):
        bind_or_verify_owner(self.db, purchase_token="token1", authenticated_owner_id="alice", now_ms=1)
        bind_or_verify_owner(self.db, purchase_token="token2", authenticated_owner_id="bob", now_ms=2)
        self.assertEqual(self.db.execute("SELECT count(*) FROM play_token_owners").fetchone()[0], 2)
    def test_binding_persists_across_connections(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "owner-ledger.sqlite3")
            with sqlite3.connect(path) as first:
                initialize(first)
                bind_or_verify_owner(first, purchase_token="persist-token",
                                     authenticated_owner_id="alice", now_ms=1)
            with sqlite3.connect(path) as second:
                with self.assertRaises(OwnershipConflict):
                    bind_or_verify_owner(second, purchase_token="persist-token",
                                         authenticated_owner_id="bob", now_ms=2)
                self.assertEqual(second.execute(
                    "SELECT owner_id FROM play_token_owners WHERE token_sha256=?",
                    (token_digest("persist-token"),)).fetchone()[0], "alice")

    def test_conflicting_binding_does_not_rollback_prior_owner(self):
        bind_or_verify_owner(self.db, purchase_token="token1",
                             authenticated_owner_id="alice", now_ms=1)
        with self.assertRaises(OwnershipConflict):
            bind_or_verify_owner(self.db, purchase_token="token1",
                                 authenticated_owner_id="bob", now_ms=2)
        self.assertEqual(bind_or_verify_owner(
            self.db, purchase_token="token1",
            authenticated_owner_id="alice", now_ms=3), token_digest("token1"))

    def test_invalid_owner(self):
        with self.assertRaises(ValueError):
            bind_or_verify_owner(self.db, purchase_token="token1", authenticated_owner_id="", now_ms=1)
    def test_invalid_time(self):
        with self.assertRaises(ValueError):
            bind_or_verify_owner(self.db, purchase_token="token1", authenticated_owner_id="alice", now_ms=True)


if __name__ == "__main__": unittest.main()
