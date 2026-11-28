"""Regression checks: unsigned AAB evidence never becomes a fake Play acceptance."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from scripts.android_bundle_artifact import record_unsigned_bundle

SHA = "a" * 40


class AndroidBundleEvidenceTest(unittest.TestCase):
    def make_bundle(self, path: Path, *, manifest=True, signature=False):
        with ZipFile(path, "w") as archive:
            if manifest:
                archive.writestr("base/manifest/AndroidManifest.xml", b"manifest")
            archive.writestr("base/dex/classes.dex", b"bytecode")
            if signature:
                archive.writestr("META-INF/KEY.RSA", b"signature")

    def test_records_hash_and_explicitly_unsigned_status(self):
        with TemporaryDirectory() as work:
            root = Path(work)
            bundle = root / "app-release.aab"
            self.make_bundle(bundle)
            data = record_unsigned_bundle(bundle, root / "out", SHA, SHA)
            copied = root / "out/app-release-unsigned.aab"
            self.assertEqual(data["sha256"], hashlib.sha256(copied.read_bytes()).hexdigest())
            self.assertEqual(data["signing_status"], "UNSIGNED")
            self.assertFalse(data["play_upload_ready"])
            self.assertFalse(data["play_console_validated"])
            self.assertEqual(json.loads((root / "out/aab-metadata.json").read_text()), data)
            self.assertEqual((root / "out/AAB-SHA256SUMS").read_text(), f"{data['sha256']}  app-release-unsigned.aab\n")

    def test_rejects_mismatched_commit(self):
        with TemporaryDirectory() as work:
            path = Path(work) / "app-release.aab"
            self.make_bundle(path)
            with self.assertRaisesRegex(ValueError, "SOURCE_SHA_MISMATCH"):
                record_unsigned_bundle(path, Path(work) / "out", "b" * 40, SHA)

    def test_rejects_missing_bundle_manifest(self):
        with TemporaryDirectory() as work:
            path = Path(work) / "app-release.aab"
            self.make_bundle(path, manifest=False)
            with self.assertRaisesRegex(ValueError, "AAB_MANIFEST_MISSING"):
                record_unsigned_bundle(path, Path(work) / "out", SHA, SHA)

    def test_rejects_unexpected_signing_material(self):
        with TemporaryDirectory() as work:
            path = Path(work) / "app-release.aab"
            self.make_bundle(path, signature=True)
            with self.assertRaisesRegex(ValueError, "AAB_UNEXPECTED_SIGNATURE"):
                record_unsigned_bundle(path, Path(work) / "out", SHA, SHA)

    def test_rejects_non_zip(self):
        with TemporaryDirectory() as work:
            path = Path(work) / "app-release.aab"
            path.write_bytes(b"not zip")
            with self.assertRaisesRegex(ValueError, "AAB_ZIP_INVALID"):
                record_unsigned_bundle(path, Path(work) / "out", SHA, SHA)


if __name__ == "__main__":
    unittest.main()
