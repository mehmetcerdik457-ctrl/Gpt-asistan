"""Real local-fixture tests for the read-only source inventory."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from server.resource_discovery import discover


class ResourceDiscoveryTests(unittest.TestCase):
    def test_hash_real_file_without_claiming_working_apk(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / "old.apk"
            original.write_bytes(b"sample APK placeholder, NOT installable")
            got = discover(tmp)
            item = got["records"][0]
            self.assertEqual(item["status"], "VERIFIED_FILE")
            self.assertEqual(item["format_hint"], "android_apk")
            self.assertEqual(item["capability_status"], "UNTESTED")
            self.assertEqual(item["integration_status"], "NOT_CONNECTED")
            self.assertEqual(item["sha256"], hashlib.sha256(original.read_bytes()).hexdigest())
            self.assertTrue(got["read_only"])

    def test_duplicate_hash_is_marked_not_falsely_counted_as_unique(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.gguf").write_bytes(b"same")
            (Path(tmp) / "b.gguf").write_bytes(b"same")
            a, b = discover(tmp)["records"]
            self.assertEqual(a["status"], "VERIFIED_FILE")
            self.assertEqual(b["duplicate_of"], "a.gguf")
            self.assertEqual(a["sha256"], b["sha256"])

    def test_secret_file_is_not_hashed_or_opened(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".env").write_text("SECRET=do-not-read")
            (Path(tmp) / "signer.keystore").write_bytes(b"private")
            results = discover(tmp)["records"]
            self.assertEqual(len(results), 2)
            self.assertTrue(all(x["reason"] == "SENSITIVE_NAME" for x in results))
            self.assertTrue(all("sha256" not in x for x in results))

    def test_symlink_never_follows_external_file(self):
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent) / "input"
            root.mkdir()
            private = Path(parent) / "private.txt"
            private.write_bytes(b"do not read me")
            (root / "external.txt").symlink_to(private)
            item = discover(root)["records"][0]
            self.assertEqual(item["status"], "BLOCKED")
            self.assertEqual(item["reason"], "NOT_REGULAR_FILE_OR_SYMLINK")
            self.assertNotIn("sha256", item)

    def test_symlink_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real"
            real.mkdir()
            link = Path(tmp) / "link"
            link.symlink_to(real)
            with self.assertRaises(ValueError):
                discover(link)

    def test_large_file_is_not_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "big.zip").write_bytes(b"a" * 101)
            item = discover(tmp, max_file_bytes=100)["records"][0]
            self.assertEqual(item["reason"], "FILE_LIMIT_EXCEEDED")
            self.assertNotIn("sha256", item)

    def test_total_budget_blocks_second_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.onnx").write_bytes(b"1111")
            (Path(tmp) / "b.onnx").write_bytes(b"2222")
            first, second = discover(tmp, max_total_bytes=4)["records"]
            self.assertEqual(first["status"], "VERIFIED_FILE")
            self.assertEqual(second["reason"], "TOTAL_LIMIT_EXCEEDED")

    def test_hidden_dependency_folder_is_pruned(self):
        with tempfile.TemporaryDirectory() as tmp:
            hidden = Path(tmp) / ".git"
            hidden.mkdir()
            (hidden / "config").write_text("do not scan")
            (Path(tmp) / "normal.py").write_text("print('not executed')")
            got = discover(tmp)
            self.assertEqual(len(got["records"]), 1)
            self.assertEqual(got["records"][0]["source_id"], "normal.py")
            self.assertEqual(got["ignored_directories"], 1)

    def test_scan_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample = root / "old.jar"
            sample.write_bytes(b"payload")
            before = (sample.read_bytes(), sample.stat().st_mtime_ns, set(root.iterdir()))
            discover(root)
            after = (sample.read_bytes(), sample.stat().st_mtime_ns, set(root.iterdir()))
            self.assertEqual(before, after)

    def test_max_files_reports_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            for n in range(3):
                (Path(tmp) / f"{n}.apk").write_bytes(str(n).encode())
            got = discover(tmp, max_files=1)
            self.assertEqual(len(got["records"]), 1)
            self.assertTrue(got["scan_truncated"])

    def test_invalid_limits_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                discover(tmp, max_total_bytes=0)


if __name__ == "__main__":
    unittest.main()
