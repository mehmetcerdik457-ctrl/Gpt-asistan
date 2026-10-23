"""Static APK structural tests: real in-process ZIP bytes, no model mocks."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from server.apk_static_inventory import inspect_apk
from server.resource_discovery import discover


def write_zip(path, files):
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as z:
        for name, data in files:
            z.writestr(name, data)
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ApkStructureTests(unittest.TestCase):
    def test_apk_dex_abi_evidence_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "genuine-structure.apk"
            digest = write_zip(path, [
                ("AndroidManifest.xml", b"binary manifest placeholder"),
                ("classes.dex", b"dex\n035\0fake"),
                ("classes2.dex", b"dex\n035\0fake"),
                ("lib/arm64-v8a/libsqlcipher.so", b"fake-library"),
                ("lib/x86_64/libsqlcipher.so", b"fake-library")])
            got = inspect_apk(path, expected_sha256=digest)
            self.assertEqual(got["status"], "ZIP_STRUCTURE_VERIFIED")
            self.assertEqual(got["dex_count"], 2)
            self.assertEqual(got["native_abis"], ["arm64-v8a", "x86_64"])
            self.assertEqual(got["native_library_count"], 2)
            self.assertFalse(got["install_tested"])
            self.assertFalse(got["signature_verified"])
            self.assertFalse(got["model_inference_tested"])

    def test_integrates_without_claiming_working_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "reference.apk"
            write_zip(p, [("AndroidManifest.xml", b"a"),
                          ("classes.dex", b"x")])
            item = discover(tmp)["records"][0]
            self.assertEqual(item["status"], "VERIFIED_FILE")
            self.assertEqual(item["apk_structure"]["status"], "ZIP_STRUCTURE_VERIFIED")
            self.assertEqual(item["capability_status"], "UNTESTED")

    def test_nonzip_apk_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "pretend.apk"
            p.write_bytes(b"not an apk")
            got = inspect_apk(p, expected_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
            self.assertEqual(got["status"], "BLOCKED")
            self.assertEqual(got["reason"], "BadZipFile")

    def test_missing_android_manifest_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "not-android.apk"
            digest = write_zip(p, [("classes.dex", b"x")])
            self.assertEqual(inspect_apk(p, expected_sha256=digest)["status"],
                             "INVALID_APK_STRUCTURE")

    def test_changed_hash_cannot_be_relabelled(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.apk"
            write_zip(p, [("AndroidManifest.xml", b"x")])
            self.assertEqual(inspect_apk(p, expected_sha256="0" * 64)["reason"],
                             "SOURCE_HASH_CHANGED")

    def test_zip_traversal_entry_rejected_no_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "unsafe.apk"
            digest = write_zip(p, [("../evil", b"x"),
                                   ("AndroidManifest.xml", b"ok")])
            self.assertEqual(inspect_apk(p, expected_sha256=digest)["reason"],
                             "ZIP_UNSAFE_ENTRY")
            self.assertFalse((Path(tmp).parent / "evil").exists())

    def test_duplicate_zip_entry_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "duplicate.apk"
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                digest = write_zip(p, [("AndroidManifest.xml", b"1"),
                                       ("AndroidManifest.xml", b"2")])
            self.assertEqual(inspect_apk(p, expected_sha256=digest)["reason"],
                             "ZIP_DUPLICATE_ENTRY")

    def test_claimed_zip_size_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "large.apk"
            digest = write_zip(p, [("AndroidManifest.xml", b"x" * 200)])
            self.assertEqual(inspect_apk(p, expected_sha256=digest,
                             max_single_uncompressed=100)["reason"],
                             "ZIP_MEMBER_LIMIT")

    def test_zip_entry_count_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "many.apk"
            digest = write_zip(p, [("AndroidManifest.xml", b"1"),
                                   ("classes.dex", b"2")])
            self.assertEqual(inspect_apk(p, expected_sha256=digest,
                             max_entries=1)["reason"], "ZIP_ENTRY_LIMIT")

    def test_symlink_cannot_redirect_inspection(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unsupported")
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "real.apk"
            digest = write_zip(p, [("AndroidManifest.xml", b"1")])
            alias = Path(tmp) / "alias.apk"
            alias.symlink_to(p)
            self.assertEqual(inspect_apk(alias, expected_sha256=digest)["reason"],
                             "SOURCE_SYMLINK")

    def test_invalid_sha256_and_limits_are_rejected(self):
        with self.assertRaises(ValueError):
            inspect_apk("/missing", expected_sha256="not_a_hash")
        with self.assertRaises(ValueError):
            inspect_apk("/missing", expected_sha256="0"*64, max_entries=0)


if __name__ == "__main__":
    unittest.main()
