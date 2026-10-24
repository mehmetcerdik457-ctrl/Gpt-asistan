"""Regression: source path replacement must never escape the permitted root."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from server.source_owner_tool import inspect_source, SourceInspectionDenied
from server.apk_static_inventory import inspect_apk as real_inspect_apk


class AnchoredDescriptorTests(unittest.TestCase):
    def test_regular_apk_uses_one_anchored_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "safe"
            directory.mkdir()
            apk = directory / "a.apk"
            with ZipFile(apk, "w") as z:
                z.writestr("AndroidManifest.xml", b"fixture")
                z.writestr("classes.dex", b"fixture")
            original = apk.read_bytes()
            evidence = inspect_source(tmp, "safe/a.apk")
            self.assertEqual(evidence["sha256"], hashlib.sha256(original).hexdigest())
            self.assertEqual(evidence["apk_structure"]["dex_count"], 1)
            self.assertEqual(apk.read_bytes(), original)

    def test_intermediate_and_final_symlinks_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "safe").mkdir()
            (root / "safe" / "a.json").write_text("{}")
            (root / "link").symlink_to(root / "safe", target_is_directory=True)
            with self.assertRaises(SourceInspectionDenied) as error:
                inspect_source(tmp, "link/a.json")
            self.assertEqual(str(error.exception), "SOURCE_LINK_DENIED")
            (root / "alias.apk").symlink_to(root / "safe" / "a.json")
            with self.assertRaises(SourceInspectionDenied) as error:
                inspect_source(tmp, "alias.apk")
            self.assertEqual(str(error.exception), "SOURCE_LINK_DENIED")

    def test_directory_swap_after_hash_keeps_original_apk_descriptor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            safe = root / "safe"
            safe.mkdir()
            evil = root / "evil"
            evil.mkdir()
            with ZipFile(safe / "a.apk", "w") as z:
                z.writestr("AndroidManifest.xml", b"good")
                z.writestr("classes.dex", b"good")
            with ZipFile(evil / "a.apk", "w") as z:
                z.writestr("AndroidManifest.xml", b"evil")
            original = (safe / "a.apk").read_bytes()

            def replace_directory_before_apk_inspection(_path, *, expected_sha256, source_fd):
                safe.rename(root / "old-safe")
                safe.symlink_to(evil, target_is_directory=True)
                return real_inspect_apk(None, expected_sha256=expected_sha256,
                                        source_fd=source_fd)

            with patch("server.source_owner_tool.inspect_apk",
                       side_effect=replace_directory_before_apk_inspection):
                evidence = inspect_source(tmp, "safe/a.apk")
            self.assertEqual(evidence["sha256"], hashlib.sha256(original).hexdigest())
            self.assertEqual(evidence["status"], "ANALYZED_STATIC")
            self.assertEqual(evidence["apk_structure"]["dex_count"], 1)
            self.assertEqual((root / "old-safe" / "a.apk").read_bytes(), original)

    def test_python_source_is_never_executed_and_bad_limits_are_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "source.py").write_text('raise RuntimeError("MUST_NOT_RUN")')
            got = inspect_source(tmp, "source.py")
            self.assertEqual(got["status"], "VERIFIED_FILE")
            self.assertEqual(got["capability_status"], "UNTESTED")
            for value in (0, -1, True):
                with self.subTest(value=value):
                    with self.assertRaises(SourceInspectionDenied):
                        inspect_source(tmp, "source.py", max_file_bytes=value)


if __name__ == "__main__":
    unittest.main()
