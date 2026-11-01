"""Independent real sqlite-vec/FTS5 hybrid retrieval tests (no cloud access)."""
import tempfile
import unittest
from pathlib import Path

from server import gateway, kral_memory


class HybridMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = gateway.Store(str(Path(self.temp.name) / "kral-memory.db"))

    def tearDown(self):
        self.temp.cleanup()

    def test_sparse_plus_dense_memory_retrieval_after_reopen(self):
        first = self.db.remember("Kırmızı elma", embedding=[0.0] * 384)
        second = self.db.remember("Mavi defter", embedding=[1.0] * 384)
        self.assertNotEqual(first, second)
        reopened = gateway.Store(str(Path(self.temp.name) / "kral-memory.db"))
        matches = reopened.recall("Kırmızı", limit=2, embedding=[0.0] * 384)
        self.assertEqual(matches[0]["text"], "Kırmızı elma")
        self.assertIn("Mavi defter", [m["text"] for m in matches])
        self.assertEqual(reopened.recall("Kırmızı", limit=2)[0]["text"], "Kırmızı elma")

    def test_invalid_embeddings_fail_before_insert(self):
        for invalid in ([0.1] * 2, [float("nan")] * 384, [True] * 384):
            with self.subTest(length=len(invalid)), self.assertRaises(ValueError):
                self.db.remember("sensitive", embedding=invalid)
        self.assertEqual(self.db.recall(), [])


if __name__ == "__main__":
    unittest.main()
